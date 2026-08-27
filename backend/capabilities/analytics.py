import calendar
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field

from backend.accounts.service import get_accounts_service
from backend.capabilities.payments import format_minor
from backend.config import settings
from backend.goals.service import get_goals_service
from backend.helpers.context import Actor
from backend.payments.service import PaymentsService, get_payments_service

_RECURRING_LOOKBACK_DAYS = 182
_RECURRING_MIN_OCCURRENCES = 3
_RECURRING_MIN_GAP_DAYS = 24
_RECURRING_MAX_GAP_DAYS = 40
_RECURRING_AMOUNT_TOLERANCE = 0.15

_GOAL_RATE_LOOKBACK_MONTHS = 3
_GOAL_STREAK_LOOKBACK_WEEKS = 26

_SIGNIFICANT_PCT_THRESHOLD = 15.0
_SIGNIFICANT_ABSOLUTE_FLOOR_MINOR = 5000

_HOME_CURRENCY = "RON"


def _add_months(base: date, months: int) -> date:
    month_index = base.month - 1 + months
    year = base.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _streak_weeks(rows: list[dict], account_id: str, now: datetime) -> int:
    buckets: dict[int, int] = defaultdict(int)
    for row in rows:
        if row["accountId"] != account_id:
            continue
        posted_at = datetime.fromisoformat(row["postedAt"])
        age_days = (now - posted_at).days
        if age_days < 0:
            continue
        buckets[age_days // 7] += row["amount"]["minorUnits"]

    streak = 0
    week = 0
    while buckets.get(week, 0) > 0:
        streak += 1
        week += 1
    return streak


async def _transactions_in_range(
    payments: PaymentsService, user_id: str, start: datetime, end: datetime
) -> list[dict]:
    collected: list[dict] = []
    cursor: str | None = None
    while True:
        page = await payments.list_transactions(user_id, cursor=cursor, limit=100)
        rows = page["transactions"]
        if not rows:
            break
        ran_out = False
        for row in rows:
            posted_at = datetime.fromisoformat(row["postedAt"])
            if posted_at < start:
                ran_out = True
                break
            if posted_at < end:
                collected.append(row)
        cursor = page["nextCursor"]
        if ran_out or cursor is None:
            break
    return collected


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc) if month == 12 else datetime(
        year, month + 1, 1, tzinfo=timezone.utc
    )
    return start, end


def _parse_month(raw: str) -> tuple[int, int]:
    year_str, month_str = raw.split("-")
    return int(year_str), int(month_str)


class CashflowForecastInput(BaseModel):
    horizon_days: int = Field(alias="horizonDays", ge=1, le=90)
    model_config = {"populate_by_name": True}


class RecurringMovement(BaseModel):
    source: str
    category: str
    amount_minor: int = Field(alias="amountMinorUnits")
    estimated_date: str = Field(alias="estimatedDate")
    model_config = {"populate_by_name": True}


class CashflowForecastOutput(BaseModel):
    status: Literal["ok", "insufficient_data"]
    current_balance_minor: int | None = Field(default=None, alias="currentBalanceMinorUnits")
    currency: str | None = None
    recurring_movements: list[RecurringMovement] = Field(
        default_factory=list, alias="recurringMovements"
    )
    projected_balance_minor: int | None = Field(default=None, alias="projectedBalanceMinorUnits")
    below_threshold: bool = Field(default=False, alias="belowThreshold")
    model_config = {"populate_by_name": True}


def _detect_recurring_groups(rows: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["counterparty"], row["category"])].append(row)

    recurring = []
    for (counterparty, category), occurrences in groups.items():
        if len(occurrences) < _RECURRING_MIN_OCCURRENCES:
            continue
        occurrences.sort(key=lambda r: r["postedAt"])
        dates = [datetime.fromisoformat(r["postedAt"]) for r in occurrences]
        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        if not all(_RECURRING_MIN_GAP_DAYS <= gap <= _RECURRING_MAX_GAP_DAYS for gap in gaps):
            continue
        amounts = [r["amount"]["minorUnits"] for r in occurrences]
        median_amount = statistics.median(amounts)
        if median_amount == 0:
            continue
        tolerance = abs(median_amount) * _RECURRING_AMOUNT_TOLERANCE
        if not all(abs(amount - median_amount) <= tolerance for amount in amounts):
            continue
        recurring.append(
            {
                "counterparty": counterparty,
                "category": category,
                "amount_minor": int(median_amount),
                "last_date": dates[-1],
                "median_gap_days": statistics.median(gaps),
            }
        )
    return recurring


async def resolve_cashflow_forecast(actor: Actor, payload: BaseModel) -> BaseModel:
    assert isinstance(payload, CashflowForecastInput)
    user_id = actor.subject_id()
    payments = get_payments_service()
    accounts = get_accounts_service()

    now = datetime.now(timezone.utc)
    lookback_start = now - timedelta(days=_RECURRING_LOOKBACK_DAYS)
    rows = [
        row
        for row in await _transactions_in_range(payments, user_id, lookback_start, now)
        if row["amount"]["currency"] == _HOME_CURRENCY
    ]

    recurring_groups = _detect_recurring_groups(rows)
    if not recurring_groups:
        return CashflowForecastOutput(status="insufficient_data")

    horizon_end = now + timedelta(days=payload.horizon_days)
    upcoming = [
        group
        for group in recurring_groups
        if now <= group["last_date"] + timedelta(days=group["median_gap_days"]) <= horizon_end
    ]

    owned = [
        account
        for account in await accounts.list_for_user(user_id)
        if account["currency"] == _HOME_CURRENCY
    ]
    current_balance = sum(account["balance"]["minorUnits"] for account in owned)

    movements = [
        RecurringMovement(
            source=group["counterparty"],
            category=group["category"],
            amountMinorUnits=group["amount_minor"],
            estimatedDate=(group["last_date"] + timedelta(days=group["median_gap_days"]))
            .date()
            .isoformat(),
        )
        for group in upcoming
    ]
    projected_balance = current_balance + sum(m.amount_minor for m in movements)

    return CashflowForecastOutput(
        status="ok",
        currentBalanceMinorUnits=current_balance,
        currency=_HOME_CURRENCY,
        recurringMovements=movements,
        projectedBalanceMinorUnits=projected_balance,
        belowThreshold=projected_balance < settings.cashflow_low_balance_threshold_minor,
    )


class GoalGapInput(BaseModel):
    goal_id: str | None = Field(default=None, alias="goalId")
    model_config = {"populate_by_name": True}


class GoalGapOutput(BaseModel):
    status: Literal["ok", "no_goal_found"]
    goal_id: str | None = Field(default=None, alias="goalId")
    name: str | None = None
    target_minor: int | None = Field(default=None, alias="targetMinorUnits")
    currency: str | None = None
    target_date: str | None = Field(default=None, alias="targetDate")
    progress_minor: int | None = Field(default=None, alias="progressMinorUnits")
    required_minor_per_month: int | None = Field(
        default=None, alias="requiredMinorUnitsPerMonth"
    )
    actual_minor_per_month: int | None = Field(default=None, alias="actualMinorUnitsPerMonth")
    gap_minor_per_month: int | None = Field(default=None, alias="gapMinorUnitsPerMonth")
    projected_completion_date: str | None = Field(
        default=None, alias="projectedCompletionDate"
    )
    streak_weeks: int = Field(default=0, alias="streakWeeks")
    model_config = {"populate_by_name": True}


async def resolve_goal_gap(actor: Actor, payload: BaseModel) -> BaseModel:
    assert isinstance(payload, GoalGapInput)
    user_id = actor.subject_id()
    progress = await get_goals_service().get_progress_for_user(user_id)
    if progress is None:
        return GoalGapOutput(status="no_goal_found")

    goal = progress.goal
    today = datetime.now(timezone.utc).date()
    months_remaining = max(
        1, (goal.target_date.year - today.year) * 12 + (goal.target_date.month - today.month)
    )
    remaining_minor = max(0, goal.target_minor - progress.progress_minor)
    required_per_month = remaining_minor // months_remaining

    payments = get_payments_service()
    now = datetime.now(timezone.utc)
    lookback_start = now - timedelta(days=30 * _GOAL_RATE_LOOKBACK_MONTHS)
    rows = await _transactions_in_range(payments, user_id, lookback_start, now)
    account_rows = [row for row in rows if row["accountId"] == goal.account_id]
    net_movement = sum(row["amount"]["minorUnits"] for row in account_rows)
    actual_per_month = net_movement // _GOAL_RATE_LOOKBACK_MONTHS

    if remaining_minor <= 0:
        projected_completion_date = today.isoformat()
    elif actual_per_month <= 0:
        projected_completion_date = None
    else:
        months_needed = -(-remaining_minor // actual_per_month)
        projected_completion_date = _add_months(today, months_needed).isoformat()

    streak_lookback_start = now - timedelta(weeks=_GOAL_STREAK_LOOKBACK_WEEKS)
    streak_rows = await _transactions_in_range(payments, user_id, streak_lookback_start, now)
    streak = _streak_weeks(streak_rows, goal.account_id, now)

    return GoalGapOutput(
        status="ok",
        goalId=goal.id,
        name=goal.name,
        targetMinorUnits=goal.target_minor,
        currency=goal.currency,
        targetDate=goal.target_date.isoformat(),
        progressMinorUnits=progress.progress_minor,
        requiredMinorUnitsPerMonth=required_per_month,
        actualMinorUnitsPerMonth=actual_per_month,
        gapMinorUnitsPerMonth=required_per_month - actual_per_month,
        projectedCompletionDate=projected_completion_date,
        streakWeeks=streak,
    )


class MonthRecapInput(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")


class BiggestExpense(BaseModel):
    amount_minor: int = Field(alias="amountMinorUnits")
    counterparty: str
    date: str
    model_config = {"populate_by_name": True}


class CategoryGrowth(BaseModel):
    category: str
    growth_pct: float = Field(alias="growthPct")
    model_config = {"populate_by_name": True}


class MonthRecapOutput(BaseModel):
    status: Literal["ok", "no_activity"]
    currency: str | None = None
    biggest_expense: BiggestExpense | None = Field(default=None, alias="biggestExpense")
    busiest_day: str | None = Field(default=None, alias="busiestDay")
    busiest_day_count: int | None = Field(default=None, alias="busiestDayCount")
    fastest_growing_category: CategoryGrowth | None = Field(
        default=None, alias="fastestGrowingCategory"
    )
    new_category_highlight: str | None = Field(default=None, alias="newCategoryHighlight")
    total_income_minor: int | None = Field(default=None, alias="totalIncomeMinorUnits")
    total_spend_minor: int | None = Field(default=None, alias="totalSpendMinorUnits")
    model_config = {"populate_by_name": True}


async def resolve_month_recap(actor: Actor, payload: BaseModel) -> BaseModel:
    assert isinstance(payload, MonthRecapInput)
    user_id = actor.subject_id()
    payments = get_payments_service()
    year, month = _parse_month(payload.month)
    start, end = _month_bounds(year, month)
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    prev_start, prev_end = _month_bounds(prev_year, prev_month)

    rows = [
        row
        for row in await _transactions_in_range(payments, user_id, start, end)
        if row["amount"]["currency"] == _HOME_CURRENCY
    ]
    if not rows:
        return MonthRecapOutput(status="no_activity")

    prev_rows = [
        row
        for row in await _transactions_in_range(payments, user_id, prev_start, prev_end)
        if row["amount"]["currency"] == _HOME_CURRENCY
    ]

    expenses = [row for row in rows if row["amount"]["minorUnits"] < 0]
    biggest = min(expenses, key=lambda row: row["amount"]["minorUnits"], default=None)

    by_day: dict[str, int] = defaultdict(int)
    for row in rows:
        by_day[row["postedAt"][:10]] += 1
    busiest_day, busiest_count = max(by_day.items(), key=lambda item: item[1])

    this_month_by_category: dict[str, int] = defaultdict(int)
    for row in expenses:
        this_month_by_category[row["category"]] += -row["amount"]["minorUnits"]
    prev_month_by_category: dict[str, int] = defaultdict(int)
    for row in prev_rows:
        if row["amount"]["minorUnits"] < 0:
            prev_month_by_category[row["category"]] += -row["amount"]["minorUnits"]

    fastest_growth_category: str | None = None
    fastest_growth_pct: float | None = None
    new_category: str | None = None
    for category, amount in this_month_by_category.items():
        prior = prev_month_by_category.get(category, 0)
        if prior == 0:
            if new_category is None:
                new_category = category
            continue
        pct = (amount - prior) / prior * 100
        if fastest_growth_pct is None or pct > fastest_growth_pct:
            fastest_growth_pct = pct
            fastest_growth_category = category

    total_income = sum(
        row["amount"]["minorUnits"] for row in rows if row["amount"]["minorUnits"] > 0
    )
    total_spend = sum(-row["amount"]["minorUnits"] for row in expenses)

    return MonthRecapOutput(
        status="ok",
        currency=_HOME_CURRENCY,
        biggestExpense=(
            BiggestExpense(
                amountMinorUnits=-biggest["amount"]["minorUnits"],
                counterparty=biggest["counterparty"],
                date=biggest["postedAt"][:10],
            )
            if biggest
            else None
        ),
        busiestDay=busiest_day,
        busiestDayCount=busiest_count,
        fastestGrowingCategory=(
            CategoryGrowth(category=fastest_growth_category, growthPct=round(fastest_growth_pct, 1))
            if fastest_growth_category
            else None
        ),
        newCategoryHighlight=new_category,
        totalIncomeMinorUnits=total_income,
        totalSpendMinorUnits=total_spend,
    )


class WhatChangedInput(BaseModel):
    period_a: str = Field(alias="periodA", pattern=r"^\d{4}-\d{2}$")
    period_b: str = Field(alias="periodB", pattern=r"^\d{4}-\d{2}$")
    category: str | None = None
    model_config = {"populate_by_name": True}


class CategoryChange(BaseModel):
    category: str
    change_pct: float = Field(alias="changePct")
    cause: Literal["new_merchant", "increased_frequency", "increased_price", "no_clear_cause"]
    top_contributors: list[str] = Field(default_factory=list, alias="topContributors")
    model_config = {"populate_by_name": True}


class WhatChangedOutput(BaseModel):
    status: Literal["ok", "insufficient_data"]
    changes: list[CategoryChange] = Field(default_factory=list)


def _spend_by_category(rows: list[dict]) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for row in rows:
        if row["amount"]["minorUnits"] < 0:
            totals[row["category"]] += -row["amount"]["minorUnits"]
    return totals


def _spend_by_merchant(rows: list[dict], category: str) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["category"] == category and row["amount"]["minorUnits"] < 0:
            grouped[row["counterparty"]].append(row)
    return grouped


def _classify_cause(
    merchants_a: dict[str, list[dict]], merchants_b: dict[str, list[dict]]
) -> tuple[str, list[str]]:
    all_merchants = set(merchants_a) | set(merchants_b)
    deltas: dict[str, int] = {}
    for merchant in all_merchants:
        spent_a = sum(-row["amount"]["minorUnits"] for row in merchants_a.get(merchant, []))
        spent_b = sum(-row["amount"]["minorUnits"] for row in merchants_b.get(merchant, []))
        deltas[merchant] = spent_b - spent_a

    total_delta = sum(deltas.values())
    if total_delta == 0:
        return "no_clear_cause", []

    ranked = sorted(deltas.items(), key=lambda item: abs(item[1]), reverse=True)
    top_contributors = [name for name, delta in ranked[:3] if delta != 0]

    top_merchant, top_delta = ranked[0]
    if abs(top_delta) < abs(total_delta) * 0.5:
        return "no_clear_cause", top_contributors

    if top_merchant not in merchants_a and top_merchant in merchants_b:
        return "new_merchant", top_contributors

    count_a = len(merchants_a.get(top_merchant, []))
    count_b = len(merchants_b.get(top_merchant, []))
    avg_a = (
        sum(-row["amount"]["minorUnits"] for row in merchants_a.get(top_merchant, [])) / count_a
        if count_a
        else 0
    )
    avg_b = (
        sum(-row["amount"]["minorUnits"] for row in merchants_b.get(top_merchant, [])) / count_b
        if count_b
        else 0
    )

    if count_a and count_b:
        if count_b > count_a and avg_a and abs(avg_b - avg_a) <= avg_a * 0.15:
            return "increased_frequency", top_contributors
        if abs(count_b - count_a) <= max(1, round(count_a * 0.2)) and avg_a and avg_b > avg_a * 1.15:
            return "increased_price", top_contributors

    return "no_clear_cause", top_contributors


async def resolve_what_changed(actor: Actor, payload: BaseModel) -> BaseModel:
    assert isinstance(payload, WhatChangedInput)
    user_id = actor.subject_id()
    payments = get_payments_service()

    year_a, month_a = _parse_month(payload.period_a)
    year_b, month_b = _parse_month(payload.period_b)
    start_a, end_a = _month_bounds(year_a, month_a)
    start_b, end_b = _month_bounds(year_b, month_b)

    rows_a = [
        row
        for row in await _transactions_in_range(payments, user_id, start_a, end_a)
        if row["amount"]["currency"] == _HOME_CURRENCY
    ]
    rows_b = [
        row
        for row in await _transactions_in_range(payments, user_id, start_b, end_b)
        if row["amount"]["currency"] == _HOME_CURRENCY
    ]
    if not rows_a and not rows_b:
        return WhatChangedOutput(status="insufficient_data")

    totals_a = _spend_by_category(rows_a)
    totals_b = _spend_by_category(rows_b)
    categories = {payload.category} if payload.category else set(totals_a) | set(totals_b)

    changes: list[CategoryChange] = []
    for category in categories:
        spent_a = totals_a.get(category, 0)
        spent_b = totals_b.get(category, 0)
        delta = spent_b - spent_a
        if abs(delta) < _SIGNIFICANT_ABSOLUTE_FLOOR_MINOR:
            continue
        pct = (delta / spent_a * 100) if spent_a else 100.0
        if spent_a and abs(pct) < _SIGNIFICANT_PCT_THRESHOLD:
            continue
        cause, contributors = _classify_cause(
            _spend_by_merchant(rows_a, category), _spend_by_merchant(rows_b, category)
        )
        changes.append(
            CategoryChange(
                category=category, changePct=round(pct, 1), cause=cause, topContributors=contributors
            )
        )

    changes.sort(key=lambda change: abs(change.change_pct), reverse=True)
    return WhatChangedOutput(status="ok", changes=changes)


class RecommendationsInput(BaseModel):
    pass


class Recommendation(BaseModel):
    kind: Literal["savings_rate", "spending_cap", "category_alert", "goal_projection"]
    category: str | None = None
    current_value_minor: int | None = Field(default=None, alias="currentValueMinorUnits")
    suggested_value_minor: int | None = Field(default=None, alias="suggestedValueMinorUnits")
    message_data: dict = Field(default_factory=dict, alias="messageData")
    model_config = {"populate_by_name": True}


class RecommendationsOutput(BaseModel):
    status: Literal["ok", "insufficient_data"]
    recommendations: list[Recommendation] = Field(default_factory=list)


async def resolve_recommendations(actor: Actor, payload: BaseModel) -> BaseModel:
    assert isinstance(payload, RecommendationsInput)
    user_id = actor.subject_id()
    recommendations: list[Recommendation] = []

    goal_gap = await resolve_goal_gap(actor, GoalGapInput())
    assert isinstance(goal_gap, GoalGapOutput)
    if goal_gap.status == "ok":
        recommendations.append(
            Recommendation(
                kind="goal_projection",
                messageData={
                    "goalName": goal_gap.name,
                    "currency": goal_gap.currency,
                    "targetDate": goal_gap.target_date,
                    "projectedCompletionDate": goal_gap.projected_completion_date,
                    "streakWeeks": goal_gap.streak_weeks,
                },
            )
        )
        recommendations.append(
            Recommendation(
                kind="savings_rate",
                currentValueMinorUnits=goal_gap.actual_minor_per_month,
                suggestedValueMinorUnits=goal_gap.required_minor_per_month,
                messageData={
                    "currency": goal_gap.currency,
                    "currentValueFormatted": format_minor(
                        goal_gap.actual_minor_per_month or 0, goal_gap.currency or _HOME_CURRENCY
                    ),
                    "suggestedValueFormatted": format_minor(
                        goal_gap.required_minor_per_month or 0,
                        goal_gap.currency or _HOME_CURRENCY,
                    ),
                    "gapMinorUnits": goal_gap.gap_minor_per_month,
                    "gapFormatted": format_minor(
                        goal_gap.gap_minor_per_month or 0, goal_gap.currency or _HOME_CURRENCY
                    ),
                },
            )
        )

    payments = get_payments_service()
    now = datetime.now(timezone.utc)
    last_year, last_month = (now.year - 1, 12) if now.month == 1 else (now.year, now.month - 1)
    prior_year, prior_month = (
        (last_year - 1, 12) if last_month == 1 else (last_year, last_month - 1)
    )
    start_prior, end_prior = _month_bounds(prior_year, prior_month)
    start_last, end_last = _month_bounds(last_year, last_month)

    rows_prior = [
        row
        for row in await _transactions_in_range(payments, user_id, start_prior, end_prior)
        if row["amount"]["currency"] == _HOME_CURRENCY
    ]
    rows_last = [
        row
        for row in await _transactions_in_range(payments, user_id, start_last, end_last)
        if row["amount"]["currency"] == _HOME_CURRENCY
    ]
    totals_prior = _spend_by_category(rows_prior)
    totals_last = _spend_by_category(rows_last)

    best_category: str | None = None
    best_delta = 0
    best_pct = 0.0
    for category, spent_last in totals_last.items():
        spent_prior = totals_prior.get(category, 0)
        delta = spent_last - spent_prior
        if delta < _SIGNIFICANT_ABSOLUTE_FLOOR_MINOR:
            continue
        pct = (delta / spent_prior * 100) if spent_prior else 100.0
        if spent_prior and pct < _SIGNIFICANT_PCT_THRESHOLD:
            continue
        if delta > best_delta:
            best_delta = delta
            best_category = category
            best_pct = pct

    if best_category is not None:
        recommendations.append(
            Recommendation(
                kind="category_alert",
                category=best_category,
                currentValueMinorUnits=totals_last[best_category],
                suggestedValueMinorUnits=totals_prior.get(best_category, 0),
                messageData={
                    "currency": _HOME_CURRENCY,
                    "currentValueFormatted": format_minor(totals_last[best_category], _HOME_CURRENCY),
                    "suggestedValueFormatted": format_minor(
                        totals_prior.get(best_category, 0), _HOME_CURRENCY
                    ),
                    "growthPct": round(best_pct, 1),
                    "month": f"{last_year:04d}-{last_month:02d}",
                },
            )
        )

    status: Literal["ok", "insufficient_data"] = "ok" if recommendations else "insufficient_data"
    return RecommendationsOutput(status=status, recommendations=recommendations)
