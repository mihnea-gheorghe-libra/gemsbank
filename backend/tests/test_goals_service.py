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
    UpdateStandingOrder,
    UpdateStandingOrderAmount,
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
        self._transactions: list[object] = []

    async def append(self, transaction, session=None) -> None:
        self._transactions.append(transaction)
        for entry in transaction.entries:
            self._balances[entry.account_id] = (
                self._balances.get(entry.account_id, 0) + entry.amount
            )

    async def in_range_for(self, account_ids, date_from, date_to):
        wanted = set(account_ids)
        return [
            transaction
            for transaction in self._transactions
            if any(entry.account_id in wanted for entry in transaction.entries)
            and (date_from is None or transaction.posted_at >= date_from)
            and (date_to is None or transaction.posted_at <= date_to)
        ]

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
        active = await self.list_active_for_user(user_id)
        return active[0] if active else None

    async def list_active_for_user(self, user_id: str):
        return [
            g for g in self._goals.values() if g.user_id == user_id and g.status == "active"
        ]

    async def set_streak(
        self, goal_id: str, streak_weeks, streak_last_week, computed_at, session=None
    ) -> None:
        goal = self._goals[goal_id]
        self._goals[goal_id] = goal.model_copy(
            update={
                "streak_weeks": streak_weeks,
                "streak_last_week": streak_last_week,
                "streak_computed_at": computed_at,
            }
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

    async def get_open_for_goal_and_source(self, goal_id: str, source_account_id: str):
        return next(
            (
                o
                for o in self._orders.values()
                if o.goal_id == goal_id
                and o.source_account_id == source_account_id
                and o.status in ("active", "paused")
            ),
            None,
        )

    async def list_open_for_goal(self, goal_id: str):
        return [
            o
            for o in self._orders.values()
            if o.goal_id == goal_id and o.status in ("active", "paused")
        ]

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

    async def set_amount(self, order_id: str, user_id: str, amount_minor: int, session=None) -> bool:
        order = self._orders.get(order_id)
        if order is None or order.user_id != user_id or order.status == "cancelled":
            return False
        self._orders[order_id] = order.model_copy(update={"amount_minor": amount_minor})
        return True

    async def update_details(
        self,
        order_id: str,
        user_id: str,
        *,
        source_account_id: str | None = None,
        amount_minor: int | None = None,
        frequency: str | None = None,
        session=None,
    ) -> bool:
        order = self._orders.get(order_id)
        if order is None or order.user_id != user_id or order.status == "cancelled":
            return False
        updates = {}
        if source_account_id is not None:
            updates["source_account_id"] = source_account_id
        if amount_minor is not None:
            updates["amount_minor"] = amount_minor
        if frequency is not None:
            updates["frequency"] = frequency
        self._orders[order_id] = order.model_copy(update=updates)
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


async def test_several_goals_stay_active_in_parallel_each_with_its_own_pot() -> None:
    account = _account()
    service, _, _ = _build_service(account, balance_minor=1_000_000)
    context = _context()
    first = await service._handle_create(
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
    second = await service._handle_create(
        CreateGoal(
            parent_account_id=account.id,
            name="Car",
            target_minor=1_000_000,
            target_date=date(2027, 1, 1),
            initial_deposit_minor=100_000,
        ),
        context,
        session=None,
    )

    assert first.data["accountId"] != second.data["accountId"]
    progress = await service.list_active_progress_for_user("user-1")
    assert sorted(item.goal.name for item in progress) == ["Apartment", "Car"]
    assert {item.goal.name: item.progress_minor for item in progress} == {
        "Apartment": 300_000,
        "Car": 100_000,
    }


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


async def test_closing_a_goal_sweeps_the_remaining_balance_back_and_keeps_it_in_history() -> None:
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
        CreateStandingOrder(
            goal_id=goal_id, source_account_id=account.id, amount_minor=50_000, frequency="weekly"
        ),
        context,
        session=None,
    )

    with pytest.raises(ConflictError):
        await service._handle_create_standing_order(
            CreateStandingOrder(
                goal_id=goal_id,
                source_account_id=account.id,
                amount_minor=10_000,
                frequency="monthly",
            ),
            context,
            session=None,
        )


async def test_standing_order_requires_source_account_to_match_the_goal_currency() -> None:
    account = _account()
    service, _, account_repo = _build_service(account, balance_minor=1_000_000)
    context = _context()
    eur_account = Account(
        user_id="user-1",
        iban="RO00TESTBANK0000000099",
        holder_name="Test User",
        currency="EUR",
        kind=AccountKind.CURRENT,
        label="EUR account",
    )
    await account_repo.add(eur_account)
    created = await service._handle_create(
        CreateGoal(
            parent_account_id=account.id, name="Apartment", target_minor=5_000_000, target_date=date(2028, 1, 1)
        ),
        context,
        session=None,
    )
    goal_id = created.data["goalId"]

    with pytest.raises(ValidationError):
        await service._handle_create_standing_order(
            CreateStandingOrder(
                goal_id=goal_id,
                source_account_id=eur_account.id,
                amount_minor=50_000,
                frequency="weekly",
            ),
            context,
            session=None,
        )


async def test_standing_order_amount_can_be_updated() -> None:
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
    order_result = await service._handle_create_standing_order(
        CreateStandingOrder(
            goal_id=goal_id, source_account_id=account.id, amount_minor=50_000, frequency="weekly"
        ),
        context,
        session=None,
    )
    standing_order_id = order_result.data["standingOrderId"]

    updated = await service._handle_update_standing_order_amount(
        UpdateStandingOrderAmount(standing_order_id=standing_order_id, amount_minor=75_000),
        context,
        session=None,
    )

    assert updated.data["amount"]["minorUnits"] == 75_000


async def test_standing_order_amount_cannot_be_updated_by_another_user() -> None:
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
    order_result = await service._handle_create_standing_order(
        CreateStandingOrder(
            goal_id=goal_id, source_account_id=account.id, amount_minor=50_000, frequency="weekly"
        ),
        context,
        session=None,
    )
    standing_order_id = order_result.data["standingOrderId"]

    with pytest.raises(NotFoundError):
        await service._handle_update_standing_order_amount(
            UpdateStandingOrderAmount(standing_order_id=standing_order_id, amount_minor=75_000),
            _context(user_id="user-2"),
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
        CreateStandingOrder(
            goal_id=created.data["goalId"],
            source_account_id=account.id,
            amount_minor=50_000,
            frequency="weekly",
        ),
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


async def test_streak_counts_consecutive_weeks_with_a_contribution() -> None:
    account = _account()
    service, repo, _ = _build_service(account, balance_minor=1_000_000, today=date(2026, 1, 22))
    context = _context()
    created = await service._handle_create(
        CreateGoal(
            parent_account_id=account.id,
            name="Apartment",
            target_minor=5_000_000,
            target_date=date(2028, 1, 1),
        ),
        context,
        session=None,
    )
    goal_id = created.data["goalId"]

    for day in (date(2026, 1, 8), date(2026, 1, 15), date(2026, 1, 22)):
        service._clock = service._ledger._clock = _FixedClock(day)
        await service._handle_deposit(
            DepositToGoal(goal_id=goal_id, amount_minor=10_000), context, session=None
        )

    stored = await repo.get(goal_id)
    assert stored.streak_weeks == 3
    assert stored.streak_last_week == "2026-W04"


async def test_streak_breaks_when_a_week_is_skipped() -> None:
    account = _account()
    service, repo, _ = _build_service(account, balance_minor=1_000_000, today=date(2026, 1, 22))
    context = _context()
    created = await service._handle_create(
        CreateGoal(
            parent_account_id=account.id,
            name="Apartment",
            target_minor=5_000_000,
            target_date=date(2028, 1, 1),
        ),
        context,
        session=None,
    )
    goal_id = created.data["goalId"]

    for day in (date(2026, 1, 8), date(2026, 1, 22)):
        service._clock = service._ledger._clock = _FixedClock(day)
        await service._handle_deposit(
            DepositToGoal(goal_id=goal_id, amount_minor=10_000), context, session=None
        )

    stored = await repo.get(goal_id)
    assert stored.streak_weeks == 1


async def test_closing_a_legacy_goal_never_closes_the_account_that_funds_it() -> None:
    account = _account()
    service, repo, accounts = _build_service(account, balance_minor=500_000)
    context = _context()
    created = await service._handle_create(
        CreateGoal(
            parent_account_id=account.id,
            name="Wedding",
            target_minor=5_000_000,
            target_date=date(2028, 1, 1),
        ),
        context,
        session=None,
    )
    goal_id = created.data["goalId"]
    stored = await repo.get(goal_id)
    repo._goals[goal_id] = stored.model_copy(update={"account_id": account.id})

    result = await service._handle_close(CloseGoal(goal_id=goal_id), context, session=None)

    assert result.data["sharedParentAccount"] is True
    assert result.data["sweptBackMinorUnits"] == 0
    assert (await accounts.get(account.id)).status.value == "active"
    assert (await repo.get(goal_id)).status == "closed"


async def test_multiple_standing_orders_from_different_accounts_allowed() -> None:
    account1 = _account()
    service, _, account_repo = _build_service(account1, balance_minor=1_000_000)
    context = _context()
    account2 = Account(
        user_id="user-1",
        iban="RO00TESTBANK0000000088",
        holder_name="Test User",
        currency="RON",
        kind=AccountKind.CURRENT,
        label="Secondary RON account",
    )
    await account_repo.add(account2)

    created = await service._handle_create(
        CreateGoal(
            parent_account_id=account1.id, name="Vacation", target_minor=5_000_000, target_date=date(2028, 1, 1)
        ),
        context,
        session=None,
    )
    goal_id = created.data["goalId"]

    # First standing order from account 1
    order1 = await service._handle_create_standing_order(
        CreateStandingOrder(
            goal_id=goal_id, source_account_id=account1.id, amount_minor=20_000, frequency="weekly"
        ),
        context,
        session=None,
    )
    assert order1.data["sourceAccountId"] == account1.id

    # Second standing order from account 2 (allowed!)
    order2 = await service._handle_create_standing_order(
        CreateStandingOrder(
            goal_id=goal_id, source_account_id=account2.id, amount_minor=30_000, frequency="monthly"
        ),
        context,
        session=None,
    )
    assert order2.data["sourceAccountId"] == account2.id

    all_orders = await service.get_standing_orders_for_goal(goal_id, "user-1")
    assert len(all_orders) == 2


async def test_standing_order_account_and_frequency_can_be_updated() -> None:
    account1 = _account()
    service, _, account_repo = _build_service(account1, balance_minor=1_000_000)
    context = _context()
    account2 = Account(
        user_id="user-1",
        iban="RO00TESTBANK0000000077",
        holder_name="Test User",
        currency="RON",
        kind=AccountKind.CURRENT,
        label="Secondary RON account",
    )
    await account_repo.add(account2)

    created = await service._handle_create(
        CreateGoal(
            parent_account_id=account1.id, name="House", target_minor=10_000_000, target_date=date(2028, 1, 1)
        ),
        context,
        session=None,
    )
    goal_id = created.data["goalId"]

    order = await service._handle_create_standing_order(
        CreateStandingOrder(
            goal_id=goal_id, source_account_id=account1.id, amount_minor=50_000, frequency="weekly"
        ),
        context,
        session=None,
    )
    so_id = order.data["standingOrderId"]

    updated = await service._handle_update_standing_order(
        UpdateStandingOrder(
            standing_order_id=so_id,
            source_account_id=account2.id,
            amount_minor=60_000,
            frequency="monthly",
        ),
        context,
        session=None,
    )

    assert updated.data["sourceAccountId"] == account2.id
    assert updated.data["amount"]["minorUnits"] == 60_000
    assert updated.data["frequency"] == "monthly"
