from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from backend.capabilities import analytics
from backend.goals.goal import Goal
from backend.helpers.context import Actor


def _row(
    posted_at: datetime,
    counterparty: str,
    category: str,
    minor_units: int,
    currency: str = "RON",
    account_id: str = "acc-1",
) -> dict:
    return {
        "transactionId": "tx",
        "accountId": account_id,
        "postedAt": posted_at.isoformat(),
        "kind": "internal_transfer",
        "counterparty": counterparty,
        "reference": "ref",
        "category": category,
        "status": "booked",
        "direction": "credit" if minor_units > 0 else "debit",
        "amount": {"minorUnits": minor_units, "currency": currency},
    }


class _FakePayments:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = sorted(rows, key=lambda r: r["postedAt"], reverse=True)

    async def list_transactions(self, user_id, *, direction=None, search=None, cursor=None, limit=None):
        return {"transactions": self._rows, "nextCursor": None}


class _FakeAccounts:
    def __init__(self, balances: dict[str, int], currency: str = "RON") -> None:
        self._balances = balances
        self._currency = currency

    async def list_for_user(self, user_id):
        return [
            {"currency": self._currency, "balance": {"minorUnits": minor, "currency": self._currency}}
            for minor in self._balances.values()
        ]


@dataclass(slots=True, frozen=True)
class _FakeGoalProgress:
    goal: Goal
    progress_minor: int


class _FakeGoals:
    def __init__(self, progress: _FakeGoalProgress | None) -> None:
        self._progress = progress

    async def get_progress_for_user(self, user_id):
        return self._progress


_ACTOR = Actor(kind="agent", id="analytics-agent", on_behalf_of="user-1")


async def test_cashflow_forecast_reports_insufficient_data_with_no_recurring_pattern(monkeypatch) -> None:
    monkeypatch.setattr(analytics, "get_payments_service", lambda: _FakePayments([]))
    monkeypatch.setattr(analytics, "get_accounts_service", lambda: _FakeAccounts({"acc-1": 0}))

    output = await analytics.resolve_cashflow_forecast(
        _ACTOR, analytics.CashflowForecastInput(horizonDays=30)
    )

    assert output.status == "insufficient_data"


async def test_cashflow_forecast_projects_balance_from_a_confirmed_recurring_debit(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    rows = [
        _row(now - timedelta(days=offset), "Netflix", "entertainment", -5000)
        for offset in (5, 35, 65, 95)
    ]
    monkeypatch.setattr(analytics, "get_payments_service", lambda: _FakePayments(rows))
    monkeypatch.setattr(analytics, "get_accounts_service", lambda: _FakeAccounts({"acc-1": 1_000_000}))

    output = await analytics.resolve_cashflow_forecast(
        _ACTOR, analytics.CashflowForecastInput(horizonDays=30)
    )

    assert output.status == "ok"
    assert output.current_balance_minor == 1_000_000
    assert len(output.recurring_movements) == 1
    assert output.recurring_movements[0].source == "Netflix"
    assert output.projected_balance_minor == 1_000_000 - 5000


async def test_goal_gap_reports_no_goal_found_without_a_goal(monkeypatch) -> None:
    monkeypatch.setattr(analytics, "get_goals_service", lambda: _FakeGoals(None))

    output = await analytics.resolve_goal_gap(_ACTOR, analytics.GoalGapInput())

    assert output.status == "no_goal_found"


async def test_goal_gap_computes_required_and_actual_rate(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    goal = Goal(
        user_id="user-1",
        account_id="acc-1",
        name="Apartment",
        target_minor=1_200_000,
        currency="RON",
        target_date=(now + timedelta(days=180)).date(),
    )
    progress = _FakeGoalProgress(goal=goal, progress_minor=200_000)
    monkeypatch.setattr(analytics, "get_goals_service", lambda: _FakeGoals(progress))
    rows = [_row(now - timedelta(days=10), "Self", "transfer", 300_000, account_id="acc-1")]
    monkeypatch.setattr(analytics, "get_payments_service", lambda: _FakePayments(rows))

    output = await analytics.resolve_goal_gap(_ACTOR, analytics.GoalGapInput())

    assert output.status == "ok"
    assert output.progress_minor == 200_000
    assert output.actual_minor_per_month == 100_000
    assert output.gap_minor_per_month == output.required_minor_per_month - 100_000


async def test_month_recap_reports_no_activity_for_an_empty_month(monkeypatch) -> None:
    monkeypatch.setattr(analytics, "get_payments_service", lambda: _FakePayments([]))

    output = await analytics.resolve_month_recap(_ACTOR, analytics.MonthRecapInput(month="2026-06"))

    assert output.status == "no_activity"


async def test_month_recap_finds_the_biggest_expense_and_busiest_day(monkeypatch) -> None:
    rows = [
        _row(datetime(2026, 6, 5, tzinfo=timezone.utc), "Rent Co", "utilities", -400_000),
        _row(datetime(2026, 6, 10, tzinfo=timezone.utc), "Shop A", "groceries", -5_000),
        _row(datetime(2026, 6, 10, tzinfo=timezone.utc), "Shop B", "groceries", -3_000),
        _row(datetime(2026, 6, 20, tzinfo=timezone.utc), "Employer", "income", 900_000),
    ]
    monkeypatch.setattr(analytics, "get_payments_service", lambda: _FakePayments(rows))

    output = await analytics.resolve_month_recap(_ACTOR, analytics.MonthRecapInput(month="2026-06"))

    assert output.status == "ok"
    assert output.biggest_expense.amount_minor == 400_000
    assert output.biggest_expense.counterparty == "Rent Co"
    assert output.busiest_day == "2026-06-10"
    assert output.busiest_day_count == 2
    assert output.total_income_minor == 900_000
    assert output.total_spend_minor == 408_000


async def test_what_changed_reports_insufficient_data_with_no_transactions(monkeypatch) -> None:
    monkeypatch.setattr(analytics, "get_payments_service", lambda: _FakePayments([]))

    output = await analytics.resolve_what_changed(
        _ACTOR, analytics.WhatChangedInput(periodA="2026-05", periodB="2026-06")
    )

    assert output.status == "insufficient_data"


async def test_what_changed_detects_a_brand_new_merchant_as_the_cause(monkeypatch) -> None:
    rows = [
        _row(datetime(2026, 6, 5, tzinfo=timezone.utc), "Spotify", "entertainment", -3_000),
        _row(datetime(2026, 6, 12, tzinfo=timezone.utc), "NewStreamCo", "entertainment", -8_000),
        _row(datetime(2026, 6, 19, tzinfo=timezone.utc), "AnotherNewCo", "entertainment", -8_000),
        _row(datetime(2026, 5, 5, tzinfo=timezone.utc), "Spotify", "entertainment", -3_000),
    ]
    monkeypatch.setattr(analytics, "get_payments_service", lambda: _FakePayments(rows))

    output = await analytics.resolve_what_changed(
        _ACTOR, analytics.WhatChangedInput(periodA="2026-05", periodB="2026-06")
    )

    assert output.status == "ok"
    entertainment = next(c for c in output.changes if c.category == "entertainment")
    assert entertainment.cause == "new_merchant"
    assert "NewStreamCo" in entertainment.top_contributors
