from datetime import datetime
from functools import lru_cache
from typing import Any, Protocol

from motor.motor_asyncio import AsyncIOMotorClientSession

from backend.accounts.account import Account, AccountKind
from backend.accounts.adapters import STARTER_ACCOUNTS, SystemClock
from backend.accounts.validation import generate_iban, normalise_iban
from backend.database.repositories import MongoAccountRepository
from backend.helpers.errors import NotFoundError
from backend.ledger.service import LedgerService, get_ledger_service
from backend.ledger.validation import normalise_currency

__all__ = [
    "Account",
    "AccountKind",
    "AccountsService",
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


class AccountsService:
    def __init__(self, accounts: AccountRepository, ledger: LedgerService, clock: Clock) -> None:
        self._accounts = accounts
        self._ledger = ledger
        self._clock = clock

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


@lru_cache(maxsize=1)
def get_accounts_service() -> AccountsService:
    return AccountsService(
        accounts=MongoAccountRepository(),
        ledger=get_ledger_service(),
        clock=SystemClock(),
    )
