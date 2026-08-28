from datetime import date, datetime, timezone
from functools import lru_cache
from typing import Any, ClassVar, Protocol

from backend.accounts.account import AccountKind
from backend.accounts.service import AccountsService, get_accounts_service
from backend.command_bus import Command, CommandBus, CommandResult, bus
from backend.database.records import AuditRecord, DomainEvent
from backend.database.repositories import MongoTermDepositRepository
from backend.deposits import validation
from backend.deposits.deposit import TermDeposit
from backend.exchange.service import ExchangeService, get_exchange_service
from backend.helpers.context import ActorContext
from backend.helpers.errors import IllegalTransitionError, NotFoundError
from backend.ledger.service import LedgerService, get_ledger_service
from motor.motor_asyncio import AsyncIOMotorClientSession

__all__ = ["TermDeposit", "TermDepositsService", "get_term_deposits_service"]


class TermDepositRepository(Protocol):
    async def add(
        self, deposit: TermDeposit, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def get(self, deposit_id: str) -> TermDeposit | None: ...

    async def list_for_user(self, user_id: str) -> list[TermDeposit]: ...

    async def close(
        self,
        deposit_id: str,
        user_id: str,
        closed_at: datetime,
        session: AsyncIOMotorClientSession | None = None,
    ) -> bool: ...


class Clock(Protocol):
    def today(self) -> date: ...


def _add_months(today: date, months: int) -> date:
    month_index = today.month - 1 + months
    year = today.year + month_index // 12
    month = month_index % 12 + 1
    day = min(today.day, 28) if month == 2 else today.day
    try:
        return date(year, month, day)
    except ValueError:
        return date(year, month, 1)


class SystemClock:
    def today(self) -> date:
        return datetime.now(timezone.utc).date()


class CreateTermDeposit(Command):
    command_name: ClassVar[str] = "deposits.create"

    parent_account_id: str
    name: str
    term_months: int
    initial_deposit_minor: int


class TopUpTermDeposit(Command):
    command_name: ClassVar[str] = "deposits.topup"

    deposit_id: str
    amount_minor: int
    source_account_id: str | None = None


class WithdrawFromTermDeposit(Command):
    command_name: ClassVar[str] = "deposits.withdraw"

    deposit_id: str
    amount_minor: int


class CloseTermDeposit(Command):
    command_name: ClassVar[str] = "deposits.close"

    deposit_id: str


class TermDepositsService:
    def __init__(
        self,
        deposits: TermDepositRepository,
        accounts: AccountsService,
        ledger: LedgerService,
        exchange: ExchangeService,
        clock: Clock,
    ) -> None:
        self._deposits = deposits
        self._accounts = accounts
        self._ledger = ledger
        self._exchange = exchange
        self._clock = clock

    def register(self, command_bus: CommandBus) -> None:
        command_bus.register(CreateTermDeposit, self._handle_create)
        command_bus.register(TopUpTermDeposit, self._handle_topup)
        command_bus.register(WithdrawFromTermDeposit, self._handle_withdraw)
        command_bus.register(CloseTermDeposit, self._handle_close)

    async def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        deposits = await self._deposits.list_for_user(user_id)
        balances = await self._ledger.balances_of([deposit.account_id for deposit in deposits])
        return [
            deposit.public_view() | {"balance": {"minorUnits": balances.get(deposit.account_id, 0)}}
            for deposit in deposits
        ]

    async def _load_active_owned(self, deposit_id: str, user_id: str) -> TermDeposit:
        deposit = await self._deposits.get(deposit_id)
        if deposit is None or deposit.user_id != user_id:
            raise NotFoundError(
                "That deposit does not belong to you.", details={"field": "depositId"}
            )
        if deposit.status != "active":
            raise IllegalTransitionError(
                "That deposit is already closed.", details={"field": "depositId"}
            )
        return deposit

    async def _handle_create(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, CreateTermDeposit)
        user_id = context.actor.subject_id()

        parent = await self._accounts.get_owned(command.parent_account_id, user_id)
        parent.guard_can_send()
        name = validation.normalise_name(command.name)
        rate_bps = validation.rate_bps_for_term(command.term_months)
        amount = validation.normalise_movement_minor(
            command.initial_deposit_minor, "initialDepositMinorUnits"
        )

        balance = await self._ledger.balance_of(parent.id)
        parent.guard_sufficient(balance, amount)

        today = self._clock.today()
        matures_at = _add_months(today, command.term_months)

        pot = await self._accounts.open_account(
            user_id=user_id,
            holder_name=parent.holder_name,
            currency=parent.currency,
            kind=AccountKind.SAVINGS,
            label=name,
            session=session,
        )

        deposit = TermDeposit(
            user_id=user_id,
            account_id=pot.id,
            parent_account_id=parent.id,
            name=name,
            rate_bps=rate_bps,
            term_months=command.term_months,
            currency=parent.currency,
            matures_at=matures_at,
        )
        await self._deposits.add(deposit, session=session)

        await self._ledger.transfer(
            source_account_id=parent.id,
            target_account_id=pot.id,
            amount_minor=amount,
            currency=parent.currency,
            reference="Term deposit opened",
            counterparty=name,
            category="savings",
            correlation_id=context.correlation_id,
            actor=context.actor.label(),
            session=session,
        )

        after = deposit.public_view() | {"balance": {"minorUnits": amount}}
        return CommandResult(
            data=after,
            audit=AuditRecord(
                action="deposits.created",
                entity_type="termDeposit",
                entity_id=deposit.id,
                after=after,
            ),
            events=[
                DomainEvent(
                    name="deposits.created", aggregate_type="termDeposit", aggregate_id=deposit.id
                )
            ],
        )

    async def _handle_topup(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, TopUpTermDeposit)
        user_id = context.actor.subject_id()
        deposit = await self._load_active_owned(command.deposit_id, user_id)
        amount = validation.normalise_movement_minor(command.amount_minor, "amountMinorUnits")

        source = await self._accounts.get_owned(
            command.source_account_id or deposit.parent_account_id, user_id
        )
        source.guard_can_send()
        pot = await self._accounts.get_owned(deposit.account_id, user_id)
        pot.guard_can_receive()

        source_balance = await self._ledger.balance_of(source.id)
        source.guard_sufficient(source_balance, amount)
        pot_balance = await self._ledger.balance_of(pot.id)

        if source.currency == deposit.currency:
            transaction = await self._ledger.transfer(
                source_account_id=source.id,
                target_account_id=pot.id,
                amount_minor=amount,
                currency=deposit.currency,
                reference="Term deposit top-up",
                counterparty=deposit.name,
                category="savings",
                correlation_id=context.correlation_id,
                actor=context.actor.label(),
                session=session,
            )
            credited_minor = amount
        else:
            result = await self._exchange.bridge(
                session=session,
                context=context,
                source_account_id=source.id,
                target_account_id=pot.id,
                amount_minor=amount,
                source_currency=source.currency,
                target_currency=deposit.currency,
                reference="Term deposit top-up",
                counterparty=deposit.name,
                category="savings",
            )
            transaction = result.source_transaction
            credited_minor = result.target_amount_minor

        after = {
            "balance": {"minorUnits": pot_balance + credited_minor},
            "journalTransactionId": transaction.id,
        }
        return CommandResult(
            data=deposit.public_view() | after,
            audit=AuditRecord(
                action="deposits.topped_up", entity_type="termDeposit", entity_id=deposit.id, after=after
            ),
            events=[
                DomainEvent(
                    name="deposits.topped_up",
                    aggregate_type="termDeposit",
                    aggregate_id=deposit.id,
                    payload=after,
                )
            ],
        )

    async def _handle_withdraw(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, WithdrawFromTermDeposit)
        user_id = context.actor.subject_id()
        deposit = await self._load_active_owned(command.deposit_id, user_id)
        amount = validation.normalise_movement_minor(command.amount_minor, "amountMinorUnits")

        pot = await self._accounts.get_owned(deposit.account_id, user_id)
        pot.guard_can_send()
        parent = await self._accounts.get_owned(deposit.parent_account_id, user_id)
        parent.guard_can_receive()

        pot_balance = await self._ledger.balance_of(pot.id)
        pot.guard_sufficient(pot_balance, amount)

        transaction = await self._ledger.transfer(
            source_account_id=pot.id,
            target_account_id=parent.id,
            amount_minor=amount,
            currency=deposit.currency,
            reference="Term deposit withdrawal",
            counterparty=parent.label,
            category="savings",
            correlation_id=context.correlation_id,
            actor=context.actor.label(),
            session=session,
        )

        after = {
            "balance": {"minorUnits": pot_balance - amount},
            "journalTransactionId": transaction.id,
        }
        return CommandResult(
            data=deposit.public_view() | after,
            audit=AuditRecord(
                action="deposits.withdrawn", entity_type="termDeposit", entity_id=deposit.id, after=after
            ),
            events=[
                DomainEvent(
                    name="deposits.withdrawn",
                    aggregate_type="termDeposit",
                    aggregate_id=deposit.id,
                    payload=after,
                )
            ],
        )

    async def _handle_close(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, CloseTermDeposit)
        user_id = context.actor.subject_id()
        deposit = await self._load_active_owned(command.deposit_id, user_id)

        pot = await self._accounts.get_owned(deposit.account_id, user_id)
        parent = await self._accounts.get_owned(deposit.parent_account_id, user_id)
        swept_minor = 0
        pot_balance = await self._ledger.balance_of(pot.id)
        if pot_balance > 0:
            pot.guard_can_send()
            await self._ledger.transfer(
                source_account_id=pot.id,
                target_account_id=parent.id,
                amount_minor=pot_balance,
                currency=deposit.currency,
                reference="Term deposit closed — balance returned",
                counterparty=parent.label,
                category="savings",
                correlation_id=context.correlation_id,
                actor=context.actor.label(),
                session=session,
            )
            swept_minor = pot_balance

        await self._accounts.close_owned(pot.id, user_id, session=session)

        closed_at = datetime.now(timezone.utc)
        closed = await self._deposits.close(deposit.id, user_id, closed_at, session=session)
        if not closed:
            raise IllegalTransitionError(
                "That deposit is already closed.", details={"field": "depositId"}
            )

        after = deposit.public_view() | {"status": "closed", "sweptBackMinorUnits": swept_minor}
        return CommandResult(
            data=after,
            audit=AuditRecord(
                action="deposits.closed", entity_type="termDeposit", entity_id=deposit.id, after=after
            ),
            events=[
                DomainEvent(
                    name="deposits.closed", aggregate_type="termDeposit", aggregate_id=deposit.id
                )
            ],
        )


@lru_cache(maxsize=1)
def get_term_deposits_service() -> TermDepositsService:
    service = TermDepositsService(
        deposits=MongoTermDepositRepository(),
        accounts=get_accounts_service(),
        ledger=get_ledger_service(),
        exchange=get_exchange_service(),
        clock=SystemClock(),
    )
    service.register(bus)
    return service
