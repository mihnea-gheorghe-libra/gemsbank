from datetime import date, datetime, timezone

import pytest

from backend.accounts.account import Account, AccountKind
from backend.accounts.service import AccountsService
from backend.goals.service import CreateGoal, GoalsService
from backend.helpers.context import Actor, ActorContext
from backend.helpers.errors import ConflictError, NotFoundError
from backend.ledger.service import LedgerService


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
        return [a for a in self._accounts.values() if a.user_id == user_id]


class _FakeJournalRepository:
    def __init__(self, balances: dict[str, int]) -> None:
        self._balances = balances

    async def append(self, transaction, session=None) -> None:
        raise NotImplementedError

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


class _FakeGoalRepository:
    def __init__(self) -> None:
        self._goals: dict[str, object] = {}

    async def add(self, goal, session=None) -> None:
        self._goals[goal.id] = goal

    async def get(self, goal_id: str):
        return self._goals.get(goal_id)

    async def get_for_user(self, user_id: str):
        return next((g for g in self._goals.values() if g.user_id == user_id), None)


def _build_service(
    account: Account, balance_minor: int, today: date = date(2026, 1, 1)
) -> tuple[GoalsService, _FakeGoalRepository]:
    ledger = LedgerService(
        journal=_FakeJournalRepository({account.id: balance_minor}), clock=_FixedClock(today)
    )
    accounts_service = AccountsService(
        accounts=_FakeAccountRepository([account]), ledger=ledger, clock=_FixedClock(today)
    )
    goal_repo = _FakeGoalRepository()
    service = GoalsService(
        goals=goal_repo, accounts=accounts_service, ledger=ledger, clock=_FixedClock(today)
    )
    return service, goal_repo


def _account(user_id: str = "user-1") -> Account:
    return Account(
        user_id=user_id,
        iban="RO00TESTBANK0000000001",
        holder_name="Test User",
        currency="RON",
        kind=AccountKind.SAVINGS,
        label="Savings",
    )


async def test_create_goal_persists_and_returns_the_public_view() -> None:
    account = _account()
    service, repo = _build_service(account, balance_minor=0)
    context = ActorContext(actor=Actor(kind="user", id="user-1"), correlation_id="corr-1")
    command = CreateGoal(
        account_id=account.id, name="Apartment", target_minor=5_000_000, target_date=date(2028, 1, 1)
    )

    result = await service._handle_create(command, context, session=None)

    assert result.data["name"] == "Apartment"
    stored = await repo.get_for_user("user-1")
    assert stored is not None
    assert stored.target_minor == 5_000_000


async def test_create_goal_rejects_a_second_goal_for_the_same_user() -> None:
    account = _account()
    service, _ = _build_service(account, balance_minor=0)
    context = ActorContext(actor=Actor(kind="user", id="user-1"), correlation_id="corr-1")
    first = CreateGoal(
        account_id=account.id, name="Apartment", target_minor=5_000_000, target_date=date(2028, 1, 1)
    )
    await service._handle_create(first, context, session=None)

    second = CreateGoal(
        account_id=account.id, name="Car", target_minor=1_000_000, target_date=date(2027, 1, 1)
    )
    with pytest.raises(ConflictError):
        await service._handle_create(second, context, session=None)


async def test_create_goal_rejects_an_account_that_does_not_belong_to_the_user() -> None:
    account = _account(user_id="someone-else")
    service, _ = _build_service(account, balance_minor=0)
    context = ActorContext(actor=Actor(kind="user", id="user-1"), correlation_id="corr-1")
    command = CreateGoal(
        account_id=account.id, name="Apartment", target_minor=5_000_000, target_date=date(2028, 1, 1)
    )

    with pytest.raises(NotFoundError):
        await service._handle_create(command, context, session=None)


async def test_get_progress_for_user_is_none_without_a_goal() -> None:
    account = _account()
    service, _ = _build_service(account, balance_minor=0)

    assert await service.get_progress_for_user("user-1") is None


async def test_get_progress_for_user_reports_the_accounts_current_balance() -> None:
    account = _account()
    service, _ = _build_service(account, balance_minor=1_200_000)
    context = ActorContext(actor=Actor(kind="user", id="user-1"), correlation_id="corr-1")
    command = CreateGoal(
        account_id=account.id, name="Apartment", target_minor=5_000_000, target_date=date(2028, 1, 1)
    )
    await service._handle_create(command, context, session=None)

    progress = await service.get_progress_for_user("user-1")

    assert progress is not None
    assert progress.progress_minor == 1_200_000
    assert progress.goal.target_minor == 5_000_000
