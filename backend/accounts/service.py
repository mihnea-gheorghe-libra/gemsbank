from datetime import datetime
from functools import lru_cache
from typing import Any, ClassVar, Protocol

from backend.accounts.account import Account, AccountKind, AccountStatus
from backend.accounts.adapters import STARTER_ACCOUNTS, SystemClock
from backend.accounts.validation import generate_iban, normalise_iban, normalise_label
from backend.command_bus import Command, CommandBus, CommandResult, bus
from backend.database.records import AuditRecord, DomainEvent
from backend.database.repositories import (
    MongoAccountRepository,
    MongoAuthUserRepository,
)
from backend.helpers.context import ActorContext
from backend.helpers.errors import (
    IllegalTransitionError,
    NotFoundError,
    ValidationError,
)
from backend.ledger.service import LedgerService, get_ledger_service
from backend.ledger.validation import normalise_currency
from motor.motor_asyncio import AsyncIOMotorClientSession

__all__ = [
    "Account",
    "AccountKind",
    "AccountStatus",
    "AccountsService",
    "CloseAccount",
    "OpenAccount",
    "get_accounts_service",
    "normalise_iban",
]


class AccountRepository(Protocol):
    async def add(
        self, account: Account, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def get(self, account_id: str) -> Account | None: ...

    async def get_by_iban(self, iban: str) -> Account | None: ...

    async def list_for_user(self, user_id: str) -> list[Account]: ...

    async def add_owner(
        self, account_id: str, user_id: str, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def set_status(
        self,
        account_id: str,
        status: AccountStatus,
        session: AsyncIOMotorClientSession | None = None,
        reason: str | None = None,
        changed_at: datetime | None = None,
        changed_by: str | None = None,
    ) -> bool: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class ResolvedUser(Protocol):
    @property
    def display_name(self) -> str: ...


class UserDirectory(Protocol):
    async def get(self, user_id: str) -> ResolvedUser | None: ...


class OpenAccount(Command):
    command_name: ClassVar[str] = "accounts.open"

    currency: str
    kind: AccountKind
    label: str | None = None


class CloseAccount(Command):
    command_name: ClassVar[str] = "accounts.close"

    account_id: str


def _label_for(kind: AccountKind, currency: str) -> str:
    if kind is AccountKind.CURRENT:
        return "Cont curent" if currency == "RON" else f"Cont curent {currency}"
    if kind is AccountKind.INVEST:
        return "Cont investiții" if currency == "RON" else f"Cont investiții {currency}"
    if kind is AccountKind.JOINT:
        return "Cont comun" if currency == "RON" else f"Cont comun {currency}"
    return "Economii" if currency == "RON" else f"Economii {currency}"


class AccountsService:
    def __init__(
        self,
        accounts: AccountRepository,
        ledger: LedgerService,
        users: UserDirectory,
        clock: Clock,
    ) -> None:
        self._accounts = accounts
        self._ledger = ledger
        self._users = users
        self._clock = clock

    def register(self, command_bus: CommandBus) -> None:
        command_bus.register(OpenAccount, self._handle_open)
        command_bus.register(CloseAccount, self._handle_close)

    async def open_account(
        self,
        user_id: str,
        holder_name: str,
        currency: str,
        kind: AccountKind,
        label: str,
        owner_ids: list[str] | None = None,
        session: AsyncIOMotorClientSession | None = None,
    ) -> Account:
        account = Account(
            user_id=user_id,
            iban=generate_iban(),
            holder_name=holder_name,
            currency=normalise_currency(currency),
            kind=kind,
            label=label,
            opened_at=self._clock.now(),
            owner_ids=owner_ids or [],
        )
        await self._accounts.add(account, session=session)
        return account

    async def add_owner(
        self,
        account_id: str,
        user_id: str,
        session: AsyncIOMotorClientSession | None = None,
    ) -> None:
        await self._accounts.add_owner(account_id, user_id, session=session)

    async def open_starter_accounts(
        self,
        user_id: str,
        holder_name: str,
        session: AsyncIOMotorClientSession | None = None,
    ) -> list[Account]:
        opened: list[Account] = []
        for currency, kind, label in STARTER_ACCOUNTS:
            opened.append(
                await self.open_account(
                    user_id, holder_name, currency, kind, label, session=session
                )
            )
        return opened

    async def get_owned(self, account_id: str, user_id: str) -> Account:
        account = await self._accounts.get(account_id)
        if account is None or not account.is_owned_by(user_id):
            raise NotFoundError(
                "That account does not belong to you.", details={"field": "sourceAccountId"}
            )
        return account

    async def get_any(self, account_id: str) -> Account:
        account = await self._accounts.get(account_id)
        if account is None:
            raise NotFoundError(
                "There is no such account.", details={"field": "accountId"}
            )
        return account

    async def get_optional(self, account_id: str) -> Account | None:
        return await self._accounts.get(account_id)

    async def set_status_with_reason(
        self,
        account: Account,
        status: AccountStatus,
        reason: str,
        changed_by: str,
        session: AsyncIOMotorClientSession | None = None,
    ) -> Account:
        changed_at = self._clock.now()
        updated = await self._accounts.set_status(
            account.id,
            status,
            session=session,
            reason=reason,
            changed_at=changed_at,
            changed_by=changed_by,
        )
        if not updated:
            raise IllegalTransitionError(
                "That account could not be updated. Reload and try again.",
                details={"field": "accountId"},
            )
        return account.model_copy(
            update={
                "status": status,
                "status_reason": reason,
                "status_changed_at": changed_at,
                "status_changed_by": changed_by,
            }
        )

    async def view_of(self, account: Account) -> dict[str, Any]:
        return account.public_view(await self._ledger.balance_of(account.id))

    async def resolve_iban(self, raw_iban: str) -> Account | None:
        return await self._accounts.get_by_iban(normalise_iban(raw_iban))

    async def owned_accounts(self, user_id: str) -> list[Account]:
        return await self._accounts.list_for_user(user_id)

    async def close_owned(
        self,
        account_id: str,
        user_id: str,
        session: AsyncIOMotorClientSession | None = None,
    ) -> None:
        await self.get_owned(account_id, user_id)
        await self._accounts.set_status(account_id, AccountStatus.CLOSED, session=session)

    async def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        accounts = await self._accounts.list_for_user(user_id)
        balances = await self._ledger.balances_of([account.id for account in accounts])
        return [account.public_view(balances.get(account.id, 0)) for account in accounts]

    async def _handle_open(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, OpenAccount)
        if command.kind is AccountKind.JOINT:
            raise ValidationError(
                "A joint account is opened from a shared savings goal, not directly.",
                details={"field": "kind"},
            )
        user = await self._users.get(context.actor.id)
        holder_name = user.display_name if user is not None else context.actor.id
        currency = command.currency.strip().upper()
        label = normalise_label(command.label) if command.label else _label_for(command.kind, currency)

        account = await self.open_account(
            user_id=context.actor.id,
            holder_name=holder_name,
            currency=currency,
            kind=command.kind,
            label=label,
            session=session,
        )
        view = account.public_view(0)

        return CommandResult(
            data=view,
            audit=AuditRecord(
                action="accounts.opened",
                entity_type="account",
                entity_id=account.id,
                after=view,
            ),
            events=[
                DomainEvent(
                    name="accounts.opened",
                    aggregate_type="account",
                    aggregate_id=account.id,
                    payload={
                        "userId": context.actor.id,
                        "currency": account.currency,
                        "kind": account.kind.value,
                    },
                )
            ],
        )

    async def _handle_close(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, CloseAccount)
        user_id = context.actor.subject_id()
        account = await self.get_owned(command.account_id, user_id)

        if account.status is not AccountStatus.ACTIVE:
            raise IllegalTransitionError(
                f"This account is already {account.status.value}.",
                details={"field": "accountId", "status": account.status.value},
            )

        balance = await self._ledger.balance_of(account.id)
        if balance != 0:
            raise ValidationError(
                "Empty this account before closing it.",
                details={"field": "accountId", "balanceMinorUnits": balance},
            )

        before = account.public_view(balance)
        await self._accounts.set_status(account.id, AccountStatus.CLOSED, session=session)
        after = before | {"status": AccountStatus.CLOSED.value}

        return CommandResult(
            data=after,
            audit=AuditRecord(
                action="accounts.closed",
                entity_type="account",
                entity_id=account.id,
                before=before,
                after=after,
            ),
            events=[
                DomainEvent(
                    name="accounts.closed",
                    aggregate_type="account",
                    aggregate_id=account.id,
                    payload={"userId": user_id},
                )
            ],
        )


@lru_cache(maxsize=1)
def get_accounts_service() -> AccountsService:
    service = AccountsService(
        accounts=MongoAccountRepository(),
        ledger=get_ledger_service(),
        users=MongoAuthUserRepository(),
        clock=SystemClock(),
    )
    service.register(bus)
    return service
