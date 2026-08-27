from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from backend.accounts.account import Account, AccountKind
from backend.accounts.service import AccountsService
from backend.goals.service import (
    CloseGoal,
    CreateGoal,
    CreateStandingOrder,
    DepositToGoal,
    GoalsService,
    RunStandingOrder,
    WithdrawFromGoal,
)
from backend.helpers.context import Actor, ActorContext
from backend.helpers.errors import ConflictError, IllegalTransitionError, NotFoundError, ValidationError
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
    def __init__(self, display_name: str = "Test User") -> None:
        self._display_name = display_name

    async def get(self, user_id: str):
        return SimpleNamespace(display_name=self._display_name)


class _FakeGoalRepository:
    def __init__(self) -> None:
        self._goals: dict[str, object] = {}

    async def add(self, goal, session=None) -> None:
        self._goals[goal.id] = goal

    async def get(self, goal_id: str):
        return self._goals.get(goal_id)

    async def get_for_user(self, user_id: str):
        return next(
            (g for g in self._goals.values() if g.user_id == user_id and g.status == "active"),
            None,
        )

    async def close(self, goal_id: str, user_id: str, closed_at, session=None) -> bool:
        goal = self._goals.get(goal_id)
        if goal is None or goal.user_id != user_id or goal.status != "active":
            return False
        self._goals[goal_id] = goal.model_copy(update={"status": "closed", "closed_at": closed_at})
        return True


class _FakeStandingOrderRepository:
    def __init__(self) -> None:
        self._orders: dict[str, object] = {}

    async def add(self, order, session=None) -> None:
        self._orders[order.id] = order

    async def get(self, order_id: str):
        return self._orders.get(order_id)

    async def get_open_for_goal(self, goal_id: str):
        return next(
            (
                o
                for o in self._orders.values()
                if o.goal_id == goal_id and o.status in ("active", "paused")
            ),
            None,
        )

    async def list_due(self, now, limit: int = 200):
        return [
            o
            for o in self._orders.values()
            if o.status == "active" and o.next_run_at <= now
        ][:limit]

    async def set_status(self, order_id: str, user_id: str, status: str, session=None) -> bool:
        order = self._orders.get(order_id)
        if order is None or order.user_id != user_id or order.status == "cancelled":
            return False
        self._orders[order_id] = order.model_copy(update={"status": status})
        return True

    async def record_run(self, order_id: str, next_run_at, ran_at, session=None) -> None:
        order = self._orders[order_id]
        self._orders[order_id] = order.model_copy(
            update={"next_run_at": next_run_at, "last_run_at": ran_at}
        )

    async def record_failure(self, order_id: str, reason: str, failed_at, session=None) -> None:
        order = self._orders[order_id]
        self._orders[order_id] = order.model_copy(update={"last_failure_reason": reason})


def _build_service(
    account: Account, balance_minor: int, today: date = date(2026, 1, 1)
) -> tuple[GoalsService, _FakeGoalRepository, _FakeAccountRepository]:
    account_repo = _FakeAccountRepository([account])
    ledger = LedgerService(
        journal=_FakeJournalRepository({account.id: balance_minor}), clock=_FixedClock(today)
    )
    accounts_service = AccountsService(
        accounts=account_repo,
        ledger=ledger,
        users=_FakeUserDirectory(),
        clock=_FixedClock(today),
    )
    goal_repo = _FakeGoalRepository()
    service = GoalsService(
        goals=goal_repo,
        standing_orders=_FakeStandingOrderRepository(),
        accounts=accounts_service,
        ledger=ledger,
        clock=_FixedClock(today),
    )
    return service, goal_repo, account_repo


def _account(user_id: str = "user-1") -> Account:
    return Account(
        user_id=user_id,
        iban="RO00TESTBANK0000000001",
        holder_name="Test User",
        currency="RON",
        kind=AccountKind.CURRENT,
        label="Current",
    )


def _context(user_id: str = "user-1", correlation_id: str = "corr-1") -> ActorContext:
    return ActorContext(actor=Actor(kind="user", id=user_id), correlation_id=correlation_id)


async def test_create_goal_opens_a_dedicated_pot_account() -> None:
    account = _account()
    service, repo, accounts = _build_service(account, balance_minor=0)
    context = _context()
    command = CreateGoal(
        parent_account_id=account.id,
        name="Apartment",
        target_minor=5_000_000,
        target_date=date(2028, 1, 1),
    )

    result = await service._handle_create(command, context, session=None)

    assert result.data["name"] == "Apartment"
    assert result.data["parentAccountId"] == account.id
    assert result.data["accountId"] != account.id
    pot = await accounts.get(result.data["accountId"])
    assert pot is not None
    assert pot.kind is AccountKind.SAVINGS
    stored = await repo.get_for_user("user-1")
    assert stored is not None
    assert stored.target_minor == 5_000_000


async def test_create_goal_with_initial_deposit_funds_the_pot_from_the_parent() -> None:
    account = _account()
    service, _, _ = _build_service(account, balance_minor=1_000_000)
    context = _context()
    command = CreateGoal(
        parent_account_id=account.id,
        name="Apartment",
        target_minor=5_000_000,
        target_date=date(2028, 1, 1),
        initial_deposit_minor=300_000,
    )

    result = await service._handle_create(command, context, session=None)

    progress = await service.get_progress_for_user("user-1")
    assert progress is not None
    assert progress.progress_minor == 300_000
    parent_balance = await service._ledger.balance_of(account.id)
    assert parent_balance == 700_000


async def test_create_goal_rejects_initial_deposit_over_the_parent_balance() -> None:
    account = _account()
    service, _, _ = _build_service(account, balance_minor=100)
    context = _context()
    command = CreateGoal(
        parent_account_id=account.id,
        name="Apartment",
        target_minor=5_000_000,
        target_date=date(2028, 1, 1),
        initial_deposit_minor=200,
    )

    with pytest.raises(ValidationError):
        await service._handle_create(command, context, session=None)


async def test_create_goal_rejects_a_second_goal_for_the_same_user() -> None:
    account = _account()
    service, _, _ = _build_service(account, balance_minor=0)
    context = _context()
    first = CreateGoal(
        parent_account_id=account.id, name="Apartment", target_minor=5_000_000, target_date=date(2028, 1, 1)
    )
    await service._handle_create(first, context, session=None)

    second = CreateGoal(
        parent_account_id=account.id, name="Car", target_minor=1_000_000, target_date=date(2027, 1, 1)
    )
    with pytest.raises(ConflictError):
        await service._handle_create(second, context, session=None)


async def test_create_goal_rejects_an_account_that_does_not_belong_to_the_user() -> None:
    account = _account(user_id="someone-else")
    service, _, _ = _build_service(account, balance_minor=0)
    context = _context()
    command = CreateGoal(
        parent_account_id=account.id, name="Apartment", target_minor=5_000_000, target_date=date(2028, 1, 1)
    )

    with pytest.raises(NotFoundError):
        await service._handle_create(command, context, session=None)


async def test_get_progress_for_user_is_none_without_a_goal() -> None:
    account = _account()
    service, _, _ = _build_service(account, balance_minor=0)

    assert await service.get_progress_for_user("user-1") is None


async def test_deposit_moves_real_money_into_the_pot() -> None:
    account = _account()
    service, _, _ = _build_service(account, balance_minor=1_000_000)
    context = _context()
    created = await service._handle_create(
        CreateGoal(
            parent_account_id=account.id, name="Apartment", target_minor=5_000_000, target_date=date(2028, 1, 1)
        ),
        context,
        session=None,
    )
    goal_id = created.data["goalId"]

    result = await service._handle_deposit(
        DepositToGoal(goal_id=goal_id, amount_minor=250_000), context, session=None
    )

    assert result.data["progressMinorUnits"] == 250_000
    progress = await service.get_progress_for_user("user-1")
    assert progress.progress_minor == 250_000
    assert await service._ledger.balance_of(account.id) == 750_000


async def test_deposit_rejects_more_than_the_parent_holds() -> None:
    account = _account()
    service, _, _ = _build_service(account, balance_minor=1_000)
    context = _context()
    created = await service._handle_create(
        CreateGoal(
            parent_account_id=account.id, name="Apartment", target_minor=5_000_000, target_date=date(2028, 1, 1)
        ),
        context,
        session=None,
    )

    with pytest.raises(ValidationError):
        await service._handle_deposit(
            DepositToGoal(goal_id=created.data["goalId"], amount_minor=1_000_000),
            context,
            session=None,
        )


async def test_withdrawal_rejects_taking_the_pot_below_zero() -> None:
    account = _account()
    service, _, _ = _build_service(account, balance_minor=1_000_000)
    context = _context()
    created = await service._handle_create(
        CreateGoal(
            parent_account_id=account.id,
            name="Apartment",
            target_minor=5_000_000,
            target_date=date(2028, 1, 1),
            initial_deposit_minor=100_000,
        ),
        context,
        session=None,
    )

    with pytest.raises(ValidationError):
        await service._handle_withdraw(
            WithdrawFromGoal(goal_id=created.data["goalId"], amount_minor=200_000),
            context,
            session=None,
        )
    progress = await service.get_progress_for_user("user-1")
    assert progress.progress_minor == 100_000


async def test_withdrawal_moves_money_back_to_the_parent() -> None:
    account = _account()
    service, _, _ = _build_service(account, balance_minor=1_000_000)
    context = _context()
    created = await service._handle_create(
        CreateGoal(
            parent_account_id=account.id,
            name="Apartment",
            target_minor=5_000_000,
            target_date=date(2028, 1, 1),
            initial_deposit_minor=300_000,
        ),
        context,
        session=None,
    )

    result = await service._handle_withdraw(
        WithdrawFromGoal(goal_id=created.data["goalId"], amount_minor=100_000),
        context,
        session=None,
    )

    assert result.data["progressMinorUnits"] == 200_000
    assert await service._ledger.balance_of(account.id) == 800_000


async def test_closing_a_goal_sweeps_the_remaining_balance_back_and_frees_the_slot() -> None:
    account = _account()
    service, repo, accounts = _build_service(account, balance_minor=1_000_000)
    context = _context()
    created = await service._handle_create(
        CreateGoal(
            parent_account_id=account.id,
            name="Apartment",
            target_minor=5_000_000,
            target_date=date(2028, 1, 1),
            initial_deposit_minor=400_000,
        ),
        context,
        session=None,
    )
    goal_id = created.data["goalId"]

    close_result = await service._handle_close(CloseGoal(goal_id=goal_id), context, session=None)

    assert close_result.data["status"] == "closed"
    assert close_result.data["sweptBackMinorUnits"] == 400_000
    assert await service._ledger.balance_of(account.id) == 1_000_000
    assert await service.get_progress_for_user("user-1") is None
    pot = await accounts.get(created.data["accountId"])
    assert pot.status.value == "closed"

    second = await service._handle_create(
        CreateGoal(
            parent_account_id=account.id, name="Car", target_minor=1_000_000, target_date=date(2027, 1, 1)
        ),
        context,
        session=None,
    )
    assert second.data["name"] == "Car"
    stored = await repo.get(goal_id)
    assert stored.status == "closed"


async def test_closing_someone_elses_goal_is_refused() -> None:
    account = _account()
    service, _, _ = _build_service(account, balance_minor=0)
    owner_context = _context()
    created = await service._handle_create(
        CreateGoal(
            parent_account_id=account.id, name="Apartment", target_minor=5_000_000, target_date=date(2028, 1, 1)
        ),
        owner_context,
        session=None,
    )

    intruder_context = _context(user_id="user-2", correlation_id="corr-2")
    with pytest.raises(NotFoundError):
        await service._handle_close(
            CloseGoal(goal_id=created.data["goalId"]), intruder_context, session=None
        )


async def test_closing_an_already_closed_goal_is_refused() -> None:
    account = _account()
    service, _, _ = _build_service(account, balance_minor=0)
    context = _context()
    created = await service._handle_create(
        CreateGoal(
            parent_account_id=account.id, name="Apartment", target_minor=5_000_000, target_date=date(2028, 1, 1)
        ),
        context,
        session=None,
    )
    await service._handle_close(CloseGoal(goal_id=created.data["goalId"]), context, session=None)

    with pytest.raises(IllegalTransitionError):
        await service._handle_close(
            CloseGoal(goal_id=created.data["goalId"]), context, session=None
        )


async def test_standing_order_cannot_be_duplicated_for_the_same_goal() -> None:
    account = _account()
    service, _, _ = _build_service(account, balance_minor=1_000_000)
    context = _context()
    created = await service._handle_create(
        CreateGoal(
            parent_account_id=account.id, name="Apartment", target_minor=5_000_000, target_date=date(2028, 1, 1)
        ),
        context,
        session=None,
    )
    goal_id = created.data["goalId"]
    await service._handle_create_standing_order(
        CreateStandingOrder(goal_id=goal_id, amount_minor=50_000, frequency="weekly"),
        context,
        session=None,
    )

    with pytest.raises(ConflictError):
        await service._handle_create_standing_order(
            CreateStandingOrder(goal_id=goal_id, amount_minor=10_000, frequency="monthly"),
            context,
            session=None,
        )


async def test_run_due_standing_orders_skips_insufficient_funds_without_raising() -> None:
    account = _account()
    service, _, _ = _build_service(account, balance_minor=1_000)
    context = _context()
    created = await service._handle_create(
        CreateGoal(
            parent_account_id=account.id, name="Apartment", target_minor=5_000_000, target_date=date(2028, 1, 1)
        ),
        context,
        session=None,
    )
    order_result = await service._handle_create_standing_order(
        CreateStandingOrder(goal_id=created.data["goalId"], amount_minor=50_000, frequency="weekly"),
        context,
        session=None,
    )

    run_result = await service._handle_run_standing_order(
        RunStandingOrder(standing_order_id=order_result.data["standingOrderId"]),
        context,
        session=None,
    )

    assert run_result.data["status"] == "skipped"
    assert run_result.data["reason"] == "insufficient_funds"
    progress = await service.get_progress_for_user("user-1")
    assert progress.progress_minor == 0
