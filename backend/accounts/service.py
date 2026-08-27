from datetime import datetime
from functools import lru_cache
from typing import Any, ClassVar, Protocol

from motor.motor_asyncio import AsyncIOMotorClientSession

from backend.accounts.account import Account, AccountKind
from backend.accounts.adapters import STARTER_ACCOUNTS, SystemClock
from backend.accounts.validation import generate_iban, normalise_iban
from backend.command_bus import Command, CommandBus, CommandResult, bus
from backend.database.records import AuditRecord, DomainEvent
from backend.database.repositories import (
    MongoAccountRepository,
    MongoAuthUserRepository,
)
from backend.helpers.context import ActorContext
from backend.helpers.errors import NotFoundError
from backend.ledger.service import LedgerService, get_ledger_service
from backend.ledger.validation import normalise_currency

__all__ = [
    "Account",
    "AccountKind",
    "AccountsService",
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


def _label_for(kind: AccountKind, currency: str) -> str:
    if kind is AccountKind.CURRENT:
        return "Cont curent" if currency == "RON" else f"Cont curent {currency}"
    if kind is AccountKind.INVEST:
        return "Cont investiții" if currency == "RON" else f"Cont investiții {currency}"
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

    async def open_account(
        self,
        user_id: str,
        holder_name: str,
        currency: str,
        kind: AccountKind,
        label: str,
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
        )
        await self._accounts.add(account, session=session)
        return account

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
        if account is None or account.user_id != user_id:
            raise NotFoundError(
                "That account does not belong to you.", details={"field": "sourceAccountId"}
            )
        return account

    async def resolve_iban(self, raw_iban: str) -> Account | None:
        return await self._accounts.get_by_iban(normalise_iban(raw_iban))

    async def owned_accounts(self, user_id: str) -> list[Account]:
        return await self._accounts.list_for_user(user_id)

    async def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        accounts = await self._accounts.list_for_user(user_id)
        balances = await self._ledger.balances_of([account.id for account in accounts])
        return [account.public_view(balances.get(account.id, 0)) for account in accounts]

    async def _handle_open(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, OpenAccount)
        user = await self._users.get(context.actor.id)
        holder_name = user.display_name if user is not None else context.actor.id
        currency = command.currency.strip().upper()

        account = await self.open_account(
            user_id=context.actor.id,
            holder_name=holder_name,
            currency=currency,
            kind=command.kind,
            label=_label_for(command.kind, currency),
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
