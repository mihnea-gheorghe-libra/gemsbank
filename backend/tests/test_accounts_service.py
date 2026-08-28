from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from backend.accounts.account import AccountKind
from backend.accounts.service import AccountsService, OpenAccount
from backend.helpers.context import Actor, ActorContext
from backend.helpers.errors import ValidationError
from backend.ledger.service import LedgerService


class _FakeAccountRepository:
    def __init__(self) -> None:
        self._accounts: dict[str, object] = {}

    async def add(self, account, session=None) -> None:
        self._accounts[account.id] = account

    async def get(self, account_id: str):
        return self._accounts.get(account_id)

    async def get_by_iban(self, iban: str):
        return next((a for a in self._accounts.values() if a.iban == iban), None)

    async def list_for_user(self, user_id: str):
        return [a for a in self._accounts.values() if a.user_id == user_id]

    async def set_status(self, account_id: str, status, session=None) -> bool:
        return True


class _FakeJournalRepository:
    async def append(self, transaction, session=None) -> None:
        return None

    async def balances_for(self, account_ids):
        return {account_id: 0 for account_id in account_ids}

    async def page_for(self, *args, **kwargs):
        raise NotImplementedError

    async def debited_since(self, account_ids, since) -> int:
        raise NotImplementedError

    async def count_for(self, account_ids) -> int:
        return 0


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 1, 1, tzinfo=timezone.utc)

    def today(self) -> date:
        return date(2026, 1, 1)


class _FakeUserDirectory:
    async def get(self, user_id: str):
        return SimpleNamespace(display_name="Test User")


def _build_service() -> AccountsService:
    return AccountsService(
        accounts=_FakeAccountRepository(),
        ledger=LedgerService(journal=_FakeJournalRepository(), clock=_FixedClock()),
        users=_FakeUserDirectory(),
        clock=_FixedClock(),
    )


def _context() -> ActorContext:
    return ActorContext(actor=Actor(kind="user", id="user-1"), correlation_id="corr-1")


async def test_open_account_uses_the_custom_label_when_given() -> None:
    service = _build_service()
    command = OpenAccount(currency="RON", kind=AccountKind.SAVINGS, label="Vacation fund")

    result = await service._handle_open(command, _context(), session=None)

    assert result.data["label"] == "Vacation fund"


async def test_open_account_falls_back_to_the_default_label() -> None:
    service = _build_service()
    command = OpenAccount(currency="RON", kind=AccountKind.SAVINGS)

    result = await service._handle_open(command, _context(), session=None)

    assert result.data["label"] == "Economii"


async def test_open_account_rejects_a_label_that_is_only_whitespace() -> None:
    service = _build_service()
    command = OpenAccount(currency="RON", kind=AccountKind.SAVINGS, label="   ")

    with pytest.raises(ValidationError):
        await service._handle_open(command, _context(), session=None)
