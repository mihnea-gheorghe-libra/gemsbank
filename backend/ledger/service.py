from datetime import datetime
from functools import lru_cache
from typing import Any, Protocol

from motor.motor_asyncio import AsyncIOMotorClientSession

from backend.database.repositories import MongoJournalRepository
from backend.ledger.adapters import SystemClock
from backend.ledger.journal import JournalEntry, JournalTransaction, TransactionKind
from backend.ledger.validation import normalise_currency, validate_minor_units


class JournalRepository(Protocol):
    async def append(
        self, transaction: JournalTransaction, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def balances_for(self, account_ids: list[str]) -> dict[str, int]: ...

    async def page_for(
        self,
        account_ids: list[str],
        direction: str | None,
        search: str | None,
        cursor: tuple[datetime, str] | None,
        limit: int,
    ) -> list[JournalTransaction]: ...

    async def debited_since(self, account_ids: list[str], since: datetime) -> int: ...

    async def count_for(self, account_ids: list[str]) -> int: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class LedgerService:
    def __init__(self, journal: JournalRepository, clock: Clock) -> None:
        self._journal = journal
        self._clock = clock

    async def post_transaction(
        self,
        *,
        currency: str,
        kind: TransactionKind,
        legs: list[tuple[str, int]],
        reference: str,
        counterparty: str,
        category: str,
        correlation_id: str,
        actor: str,
        session: AsyncIOMotorClientSession | None = None,
    ) -> JournalTransaction:
        transaction = JournalTransaction(
            currency=normalise_currency(currency),
            kind=kind,
            entries=[
                JournalEntry(account_id=account_id, amount=amount)
                for account_id, amount in legs
            ],
            reference=reference,
            counterparty=counterparty,
            category=category,
            posted_at=self._clock.now(),
            correlation_id=correlation_id,
            actor=actor,
        )
        await self._journal.append(transaction, session=session)
        return transaction

    async def transfer(
        self,
        *,
        source_account_id: str,
        target_account_id: str,
        amount_minor: int,
        currency: str,
        reference: str,
        counterparty: str,
        category: str,
        correlation_id: str,
        actor: str,
        session: AsyncIOMotorClientSession | None = None,
    ) -> JournalTransaction:
        amount = validate_minor_units(amount_minor)
        return await self.post_transaction(
            currency=currency,
            kind=TransactionKind.INTERNAL_TRANSFER,
            legs=[(source_account_id, -amount), (target_account_id, amount)],
            reference=reference,
            counterparty=counterparty,
            category=category,
            correlation_id=correlation_id,
            actor=actor,
            session=session,
        )

    async def balance_of(self, account_id: str) -> int:
        balances = await self._journal.balances_for([account_id])
        return balances.get(account_id, 0)

    async def balances_of(self, account_ids: list[str]) -> dict[str, int]:
        if not account_ids:
            return {}
        return await self._journal.balances_for(account_ids)

    async def debited_since(self, account_ids: list[str], since: datetime) -> int:
        if not account_ids:
            return 0
        return await self._journal.debited_since(account_ids, since)

    async def count_for(self, account_ids: list[str]) -> int:
        if not account_ids:
            return 0
        return await self._journal.count_for(account_ids)

    async def movements(
        self,
        account_ids: list[str],
        *,
        direction: str | None = None,
        search: str | None = None,
        cursor: tuple[datetime, str] | None = None,
        limit: int = 25,
    ) -> tuple[list[dict[str, Any]], tuple[datetime, str] | None]:
        if not account_ids:
            return [], None
        owned = set(account_ids)
        page = await self._journal.page_for(account_ids, direction, search, cursor, limit + 1)
        has_more = len(page) > limit
        page = page[:limit]

        rows: list[dict[str, Any]] = []
        for transaction in page:
            for entry in transaction.entries:
                if entry.account_id not in owned:
                    continue
                if direction == "credit" and entry.amount < 0:
                    continue
                if direction == "debit" and entry.amount > 0:
                    continue
                rows.append(transaction.movement_view(entry.account_id))

        next_cursor = (page[-1].posted_at, page[-1].id) if has_more and page else None
        return rows, next_cursor


@lru_cache(maxsize=1)
def get_ledger_service() -> LedgerService:
    return LedgerService(journal=MongoJournalRepository(), clock=SystemClock())
