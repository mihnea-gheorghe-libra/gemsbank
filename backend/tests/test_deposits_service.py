from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from backend.accounts.account import Account, AccountKind
from backend.accounts.service import AccountsService
from backend.deposits.service import (
    CloseTermDeposit,
    CreateTermDeposit,
    TermDepositsService,
    TopUpTermDeposit,
    WithdrawFromTermDeposit,
)
from backend.exchange.service import ExchangeService
from backend.helpers.context import Actor, ActorContext
from backend.helpers.errors import (
    IllegalTransitionError,
    NotFoundError,
    ValidationError,
)
from backend.ledger.service import LedgerService


class _FakeAccountRepository:
    def __init__(self, accounts: list[Account]) -> None:
        self._accounts = {account.id: account for account in accounts}

    async def add(self, account, session=None) -> None:
        self._accounts[account.id] = account

    async def get(self, account_id: str):
        return self._accounts.get(account_id)

    async def get_by_iban(self, iban: str):
        return next((a for a in self._accounts.values() if a.iban == iban), None)

    async def list_for_user(self, user_id: str) -> list[Account]:
        return [a for a in self._accounts.values() if a.user_id == user_id]

    async def set_status(self, account_id: str, status, session=None) -> bool:
        account = self._accounts.get(account_id)
        if account is None:
            return False
        self._accounts[account_id] = account.model_copy(update={"status": status})
        return True


class _FakeJournalRepository:
    def __init__(self, balances: dict[str, int]) -> None:
        self._balances = dict(balances)

    async def append(self, transaction, session=None) -> None:
        for entry in transaction.entries:
            self._balances[entry.account_id] = (
                self._balances.get(entry.account_id, 0) + entry.amount
            )

    async def balances_for(self, account_ids: list[str]) -> dict[str, int]:
        return {account_id: self._balances.get(account_id, 0) for account_id in account_ids}

    async def page_for(self, *args, **kwargs):
        raise NotImplementedError

    async def debited_since(self, account_ids, since) -> int:
        raise NotImplementedError

    async def count_for(self, account_ids) -> int:
        return 0


class _FixedClock:
    def __init__(self, today: date) -> None:
        self._today = today

    def now(self) -> datetime:
        return datetime.combine(self._today, datetime.min.time(), tzinfo=timezone.utc)

    def today(self) -> date:
        return self._today


class _FakeUserDirectory:
    async def get(self, user_id: str):
        return SimpleNamespace(display_name="Test User")


class _UnusedRateClient:
    async def fetch(self, base: str, quote: str):
        raise AssertionError("a same-currency top-up needs no FX rate")


class _FixedRateClient:
    def __init__(self, rate_micro: int) -> None:
        self._rate_micro = rate_micro

    async def fetch(self, base: str, quote: str):
        return self._rate_micro, date(2026, 1, 1)


class _FakeDepositRepository:
    def __init__(self) -> None:
        self._deposits: dict[str, object] = {}

    async def add(self, deposit, session=None) -> None:
        self._deposits[deposit.id] = deposit

    async def get(self, deposit_id: str):
        return self._deposits.get(deposit_id)

    async def list_for_user(self, user_id: str):
        return [d for d in self._deposits.values() if d.user_id == user_id]

    async def close(self, deposit_id: str, user_id: str, closed_at, session=None) -> bool:
        deposit = self._deposits.get(deposit_id)
        if deposit is None or deposit.user_id != user_id or deposit.status != "active":
            return False
        self._deposits[deposit_id] = deposit.model_copy(
            update={"status": "closed", "closed_at": closed_at}
        )
        return True


def _account(user_id: str = "user-1", currency: str = "RON") -> Account:
    return Account(
        user_id=user_id,
        iban=f"RO00TESTBANK{currency}0000001",
        holder_name="Test User",
        currency=currency,
        kind=AccountKind.CURRENT,
        label="Current",
    )


def _context(user_id: str = "user-1") -> ActorContext:
    return ActorContext(actor=Actor(kind="user", id=user_id), correlation_id="corr-1")


def _build_service(
    account: Account,
    balance_minor: int,
    today: date = date(2026, 1, 1),
    other_accounts: list[Account] | None = None,
    other_balances: dict[str, int] | None = None,
    rates=None,
):
    account_repo = _FakeAccountRepository([account] + (other_accounts or []))
    balances = {account.id: balance_minor} | (other_balances or {})
    ledger = LedgerService(journal=_FakeJournalRepository(balances), clock=_FixedClock(today))
    accounts_service = AccountsService(
        accounts=account_repo, ledger=ledger, users=_FakeUserDirectory(), clock=_FixedClock(today)
    )
    exchange = ExchangeService(
        accounts=accounts_service, ledger=ledger, rates=rates or _UnusedRateClient()
    )
    deposit_repo = _FakeDepositRepository()
    service = TermDepositsService(
        deposits=deposit_repo,
        accounts=accounts_service,
        ledger=ledger,
        exchange=exchange,
        clock=_FixedClock(today),
    )
    return service, deposit_repo, accounts_service


async def test_create_term_deposit_opens_a_funded_pot_account() -> None:
    account = _account()
    service, _repo, accounts = _build_service(account, balance_minor=1_000_000)
    command = CreateTermDeposit(
        parent_account_id=account.id, name="12M", term_months=12, initial_deposit_minor=600_000
    )

    result = await service._handle_create(command, _context(), session=None)

    assert result.data["rateBps"] == 610
    assert result.data["balance"]["minorUnits"] == 600_000
    pot = await accounts.get_owned(result.data["accountId"], "user-1")
    assert pot.kind is AccountKind.SAVINGS
    parent_balance = await service._ledger.balance_of(account.id)
    assert parent_balance == 400_000


async def test_create_term_deposit_rejects_an_unlisted_term() -> None:
    account = _account()
    service, _, _ = _build_service(account, balance_minor=1_000_000)
    command = CreateTermDeposit(
        parent_account_id=account.id, name="Odd", term_months=13, initial_deposit_minor=100_000
    )

    with pytest.raises(ValidationError):
        await service._handle_create(command, _context(), session=None)


async def test_create_term_deposit_rejects_insufficient_balance() -> None:
    account = _account()
    service, _, _ = _build_service(account, balance_minor=100)
    command = CreateTermDeposit(
        parent_account_id=account.id, name="12M", term_months=12, initial_deposit_minor=200
    )

    with pytest.raises(ValidationError):
        await service._handle_create(command, _context(), session=None)


async def test_multiple_term_deposits_allowed_for_the_same_user() -> None:
    account = _account()
    service, repo, _ = _build_service(account, balance_minor=2_000_000)
    first = CreateTermDeposit(
        parent_account_id=account.id, name="A", term_months=6, initial_deposit_minor=500_000
    )
    second = CreateTermDeposit(
        parent_account_id=account.id, name="B", term_months=12, initial_deposit_minor=500_000
    )

    await service._handle_create(first, _context(), session=None)
    await service._handle_create(second, _context(), session=None)

    stored = await repo.list_for_user("user-1")
    assert len(stored) == 2


async def test_topup_and_withdraw_move_money_between_parent_and_pot() -> None:
    account = _account()
    service, _, _ = _build_service(account, balance_minor=1_000_000)
    created = await service._handle_create(
        CreateTermDeposit(
            parent_account_id=account.id, name="12M", term_months=12, initial_deposit_minor=500_000
        ),
        _context(),
        session=None,
    )
    deposit_id = created.data["depositId"]

    await service._handle_topup(
        TopUpTermDeposit(deposit_id=deposit_id, amount_minor=100_000), _context(), session=None
    )
    parent_after_topup = await service._ledger.balance_of(account.id)
    assert parent_after_topup == 400_000

    await service._handle_withdraw(
        WithdrawFromTermDeposit(deposit_id=deposit_id, amount_minor=50_000), _context(), session=None
    )
    parent_after_withdraw = await service._ledger.balance_of(account.id)
    assert parent_after_withdraw == 450_000


async def test_topup_accepts_a_source_account_other_than_the_original_parent() -> None:
    account = _account()
    other = _account()
    service, _, _ = _build_service(
        account, balance_minor=1_000_000, other_accounts=[other], other_balances={other.id: 200_000}
    )
    created = await service._handle_create(
        CreateTermDeposit(
            parent_account_id=account.id, name="12M", term_months=12, initial_deposit_minor=500_000
        ),
        _context(),
        session=None,
    )
    deposit_id = created.data["depositId"]

    result = await service._handle_topup(
        TopUpTermDeposit(deposit_id=deposit_id, amount_minor=50_000, source_account_id=other.id),
        _context(),
        session=None,
    )

    assert result.data["balance"]["minorUnits"] == 550_000
    assert await service._ledger.balance_of(other.id) == 150_000
    assert await service._ledger.balance_of(account.id) == 500_000


async def test_topup_from_a_different_currency_account_converts_via_the_fx_rate() -> None:
    account = _account(currency="RON")
    other = _account(currency="EUR")
    service, _, _ = _build_service(
        account,
        balance_minor=1_000_000,
        other_accounts=[other],
        other_balances={other.id: 100_000},
        rates=_FixedRateClient(5_000_000),
    )
    created = await service._handle_create(
        CreateTermDeposit(
            parent_account_id=account.id, name="12M", term_months=12, initial_deposit_minor=500_000
        ),
        _context(),
        session=None,
    )
    deposit_id = created.data["depositId"]

    result = await service._handle_topup(
        TopUpTermDeposit(deposit_id=deposit_id, amount_minor=2_000, source_account_id=other.id),
        _context(),
        session=None,
    )

    # 20.00 EUR converted at 1 EUR = 5.00 RON lands 100.00 RON on top of the 5,000.00 RON
    # the pot already held from the opening deposit.
    assert result.data["balance"]["minorUnits"] == 510_000
    assert await service._ledger.balance_of(other.id) == 98_000


async def test_close_term_deposit_sweeps_balance_back_and_closes_the_pot() -> None:
    account = _account()
    service, _repo, accounts = _build_service(account, balance_minor=1_000_000)
    created = await service._handle_create(
        CreateTermDeposit(
            parent_account_id=account.id, name="12M", term_months=12, initial_deposit_minor=500_000
        ),
        _context(),
        session=None,
    )
    deposit_id = created.data["depositId"]
    pot_id = created.data["accountId"]

    result = await service._handle_close(
        CloseTermDeposit(deposit_id=deposit_id), _context(), session=None
    )

    assert result.data["status"] == "closed"
    assert result.data["sweptBackMinorUnits"] == 500_000
    parent_balance = await service._ledger.balance_of(account.id)
    assert parent_balance == 1_000_000
    pot = await accounts._accounts.get(pot_id)
    assert pot.status.value == "closed"

    with pytest.raises(IllegalTransitionError):
        await service._handle_close(CloseTermDeposit(deposit_id=deposit_id), _context(), session=None)


async def test_movement_on_someone_elses_deposit_is_rejected() -> None:
    account = _account()
    service, _, _ = _build_service(account, balance_minor=1_000_000)
    created = await service._handle_create(
        CreateTermDeposit(
            parent_account_id=account.id, name="12M", term_months=12, initial_deposit_minor=500_000
        ),
        _context(),
        session=None,
    )
    deposit_id = created.data["depositId"]

    with pytest.raises(NotFoundError):
        await service._handle_topup(
            TopUpTermDeposit(deposit_id=deposit_id, amount_minor=1_000),
            _context(user_id="someone-else"),
            session=None,
        )
