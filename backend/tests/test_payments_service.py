from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from backend.accounts.account import Account, AccountKind
from backend.accounts.service import AccountsService
from backend.config import settings
from backend.exchange.service import ExchangeService
from backend.helpers.context import Actor, ActorContext
from backend.helpers.crypto import Argon2idHasher
from backend.helpers.errors import ValidationError
from backend.ledger.journal import TransactionKind
from backend.ledger.service import LedgerService
from backend.payments.adapters import (
    DevCodeStepUp,
    InternalPayeeVerifier,
    StaticLimitPolicy,
)
from backend.payments.payment import Payment
from backend.payments.service import MakeTransfer, PaymentsService


class _FakeAccountRepository:
    def __init__(self, accounts: list[Account]) -> None:
        self._accounts = {account.id: account for account in accounts}

    async def add(self, account, session=None) -> None:
        self._accounts[account.id] = account

    async def get(self, account_id: str) -> Account | None:
        return self._accounts.get(account_id)

    async def get_by_iban(self, iban: str) -> Account | None:
        return next((a for a in self._accounts.values() if a.iban == iban), None)

    async def list_for_user(self, user_id: str) -> list[Account]:
        return [
            a for a in self._accounts.values()
            if a.user_id == user_id or user_id in a.owner_ids
        ]

    async def add_owner(self, account_id: str, user_id: str, session=None) -> None:
        account = self._accounts.get(account_id)
        if account is not None and user_id not in account.owner_ids:
            self._accounts[account_id] = account.model_copy(
                update={"owner_ids": [*account.owner_ids, user_id]}
            )

    async def set_status(self, account_id: str, status, session=None) -> bool:
        account = self._accounts.get(account_id)
        if account is None:
            return False
        self._accounts[account_id] = account.model_copy(update={"status": status})
        return True


class _FakeJournalRepository:
    def __init__(self, balances: dict[str, int]) -> None:
        self._balances = dict(balances)
        self.transactions: list = []

    async def append(self, transaction, session=None) -> None:
        self.transactions.append(transaction)
        for entry in transaction.entries:
            self._balances[entry.account_id] = (
                self._balances.get(entry.account_id, 0) + entry.amount
            )

    async def balances_for(self, account_ids: list[str]) -> dict[str, int]:
        return {account_id: self._balances.get(account_id, 0) for account_id in account_ids}

    async def page_for(self, *args, **kwargs):
        raise NotImplementedError

    async def debited_since(self, account_ids, since) -> int:
        return 0

    async def count_for(self, account_ids) -> int:
        return 0

    async def in_range_for(self, *args, **kwargs):
        raise NotImplementedError

    async def balance_before(self, account_ids, before) -> int:
        return 0


class _FakeUserDirectory:
    async def get(self, user_id: str):
        return SimpleNamespace(display_name="Test User")


class _FakePaymentRepository:
    def __init__(self) -> None:
        self.payments: dict[str, Payment] = {}

    async def add(self, payment: Payment, session=None) -> None:
        self.payments[payment.id] = payment

    async def get(self, payment_id: str) -> Payment | None:
        return self.payments.get(payment_id)

    async def save(self, payment: Payment, session=None) -> None:
        self.payments[payment.id] = payment

    async def list_by_status(self, user_id: str, status) -> list[Payment]:
        return [p for p in self.payments.values() if p.user_id == user_id and p.status == status]

    async def count_by_status(self, user_id: str, status) -> int:
        return len(await self.list_by_status(user_id, status))

    async def ibans_by_journal_transaction_ids(self, journal_transaction_ids: list[str]):
        return {}


class _UnusedRepository:
    async def add(self, *args, **kwargs):
        raise AssertionError("not used by these tests")

    async def list_for_user(self, *args, **kwargs):
        return []

    async def find(self, *args, **kwargs):
        return None

    async def get(self, *args, **kwargs):
        return None

    async def update(self, *args, **kwargs):
        raise AssertionError("not used by these tests")

    async def delete(self, *args, **kwargs):
        raise AssertionError("not used by these tests")


class _UnusedAuth:
    async def verify_user_pin(self, user_id: str, pin: str) -> bool:
        raise AssertionError("not used outside the step-up path")


class _FixedRateClient:
    def __init__(self, rate_micro: int) -> None:
        self._rate_micro = rate_micro

    async def fetch(self, base: str, quote: str) -> tuple[int, date]:
        return self._rate_micro, date(2026, 1, 1)


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _account(user_id: str = "user-1", currency: str = "RON") -> Account:
    return Account(
        user_id=user_id,
        iban=f"RO00TESTBANK{currency}0000001",
        holder_name="Test User",
        currency=currency,
        kind=AccountKind.CURRENT,
        label="Cont curent",
    )


def _context(user_id: str = "user-1") -> ActorContext:
    return ActorContext(actor=Actor(kind="user", id=user_id), correlation_id="corr-1")


def _build_service(
    accounts: list[Account], balances: dict[str, int], rate_micro: int = 5_000_000
) -> tuple[PaymentsService, LedgerService, _FakeJournalRepository]:
    account_repo = _FakeAccountRepository(accounts)
    journal = _FakeJournalRepository(balances)
    ledger = LedgerService(journal=journal, clock=_FixedClock(datetime(2026, 1, 1, tzinfo=timezone.utc)))
    accounts_service = AccountsService(
        accounts=account_repo,
        ledger=ledger,
        users=_FakeUserDirectory(),
        clock=_FixedClock(datetime(2026, 1, 1, tzinfo=timezone.utc)),
    )
    exchange = ExchangeService(
        accounts=accounts_service, ledger=ledger, rates=_FixedRateClient(rate_micro)
    )
    service = PaymentsService(
        payments=_FakePaymentRepository(),
        beneficiaries=_UnusedRepository(),
        templates=_UnusedRepository(),
        accounts=accounts_service,
        ledger=ledger,
        exchange=exchange,
        policy=StaticLimitPolicy(settings),
        step_up=DevCodeStepUp(settings),
        payees=InternalPayeeVerifier(),
        hasher=Argon2idHasher(),
        auth=_UnusedAuth(),
        clock=_FixedClock(datetime(2026, 1, 1, tzinfo=timezone.utc)),
        config=settings,
    )
    return service, ledger, journal


async def test_transfer_between_same_currency_accounts_moves_the_exact_amount() -> None:
    source = _account(currency="RON")
    target = _account(currency="RON")
    service, ledger, journal = _build_service([source, target], {source.id: 100_000})
    context = _context()

    result = await service._handle_transfer(
        MakeTransfer(
            source_account_id=source.id,
            target_account_id=target.id,
            counterparty="Test User",
            amount_minor=20_000,
            reference="Test",
        ),
        context,
        session=None,
    )

    assert result.data["status"] == "posted"
    assert await ledger.balance_of(source.id) == 80_000
    assert await ledger.balance_of(target.id) == 20_000
    assert all(tx.kind is TransactionKind.INTERNAL_TRANSFER for tx in journal.transactions)


async def test_transfer_across_currencies_converts_via_the_fx_rate_and_lands_the_converted_amount() -> None:
    source = _account(currency="RON")
    target = _account(currency="EUR")
    service, ledger, journal = _build_service(
        [source, target], {source.id: 100_000}, rate_micro=200_000  # 1 RON = 0.2 EUR
    )
    context = _context()

    result = await service._handle_transfer(
        MakeTransfer(
            source_account_id=source.id,
            target_account_id=target.id,
            counterparty="Test User",
            amount_minor=10_000,
            reference="Test",
        ),
        context,
        session=None,
    )

    assert result.data["status"] == "posted"
    assert result.data["amount"] == {"minorUnits": 10_000, "currency": "RON"}
    assert result.data["convertedAmount"] == {
        "minorUnits": 2_000,
        "currency": "EUR",
        "rateMicro": 200_000,
    }
    assert await ledger.balance_of(source.id) == 90_000
    assert await ledger.balance_of(target.id) == 2_000
    assert all(tx.kind is TransactionKind.FX_CONVERSION for tx in journal.transactions)
    assert {tx.currency for tx in journal.transactions} == {"RON", "EUR"}


async def test_transfer_across_currencies_still_checks_the_source_balance_in_source_currency() -> None:
    source = _account(currency="RON")
    target = _account(currency="EUR")
    service, _, _ = _build_service([source, target], {source.id: 1_000}, rate_micro=200_000)
    context = _context()

    with pytest.raises(ValidationError):
        await service._handle_transfer(
            MakeTransfer(
                source_account_id=source.id,
                target_account_id=target.id,
                counterparty="Test User",
                amount_minor=10_000,
                reference="Test",
            ),
            context,
            session=None,
        )
