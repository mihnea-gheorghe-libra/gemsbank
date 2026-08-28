from datetime import date, datetime, timezone
from typing import Literal

from backend.accounts.service import AccountsService, get_accounts_service
from backend.capabilities import analytics as analytics_capabilities
from backend.capabilities.education_docs import search_education_docs
from backend.capabilities.payments import (
    AccountBalance,
    ProposalBlocker,
    _resolve_ref,
    _to_balance,
    format_minor,
)
from backend.goals import validation as goals_validation
from backend.goals.service import GoalsService, get_goals_service
from backend.helpers.context import Actor
from backend.helpers.errors import ValidationError
from pydantic import BaseModel, Field


class EducationSearchInput(BaseModel):
    query: str = Field(default="", max_length=200)


class EducationDocView(BaseModel):
    id: str
    label_en: str = Field(alias="labelEn")
    label_ro: str = Field(alias="labelRo")
    body_en: str = Field(alias="bodyEn")
    body_ro: str = Field(alias="bodyRo")
    model_config = {"populate_by_name": True}


class EducationSearchOutput(BaseModel):
    results: list[EducationDocView]


async def resolve_education_search(_actor: Actor, payload: BaseModel) -> BaseModel:
    assert isinstance(payload, EducationSearchInput)
    docs = search_education_docs(payload.query)
    return EducationSearchOutput(
        results=[
            EducationDocView(
                id=doc.id,
                labelEn=doc.label_en,
                labelRo=doc.label_ro,
                bodyEn=doc.body_en,
                bodyRo=doc.body_ro,
            )
            for doc in docs
        ]
    )


class GoalProposalInput(BaseModel):
    account_ref: str = Field(
        alias="accountRef",
        max_length=64,
        description=(
            "The account to fund the goal from, in the user's own words: a label such as "
            "'current', a currency such as 'RON', or the last digits of an IBAN."
        ),
    )
    name: str = Field(max_length=80, description="A short name for the goal.")
    target_minor: int = Field(
        alias="targetMinorUnits",
        ge=1,
        description="The target amount in integer minor units: 3.000,00 RON is 300000.",
    )
    target_date: date = Field(
        alias="targetDate", description="The date the goal should be reached by."
    )
    currency: str | None = Field(
        default=None,
        max_length=3,
        description=(
            "The ISO 4217 code of the currency the customer named the target amount in: "
            "'5.000 lei' is RON, '400 euro' is EUR. Pass it whenever they named one — it is "
            "what separates two accounts that answer to the same description."
        ),
    )
    model_config = {"populate_by_name": True}


class GoalProposalOutput(BaseModel):
    status: Literal["proposed", "blocked", "needs_clarification"]
    proposal_kind: Literal["goal"] = Field(default="goal", alias="proposalKind")
    proposal_id: str | None = Field(default=None, alias="proposalId")
    account_id: str | None = Field(default=None, alias="accountId")
    account_label: str | None = Field(default=None, alias="accountLabel")
    currency: str | None = None
    name: str | None = None
    target_minor: int | None = Field(default=None, alias="targetMinorUnits")
    target_formatted: str | None = Field(default=None, alias="targetFormatted")
    target_date: date | None = Field(default=None, alias="targetDate")
    days_remaining: int | None = Field(default=None, alias="daysRemaining")
    weeks_remaining: int | None = Field(default=None, alias="weeksRemaining")
    months_remaining: int | None = Field(default=None, alias="monthsRemaining")
    suggested_monthly_minor: int | None = Field(
        default=None, alias="suggestedMonthlyMinorUnits"
    )
    suggested_monthly_formatted: str | None = Field(
        default=None, alias="suggestedMonthlyFormatted"
    )
    suggested_weekly_minor: int | None = Field(
        default=None, alias="suggestedWeeklyMinorUnits"
    )
    suggested_weekly_formatted: str | None = Field(
        default=None, alias="suggestedWeeklyFormatted"
    )
    requires_human_confirmation: bool = Field(default=True, alias="requiresHumanConfirmation")
    candidates: list[AccountBalance] = Field(default_factory=list)
    blockers: list[ProposalBlocker] = Field(default_factory=list)
    model_config = {"populate_by_name": True}


async def resolve_goal_proposal(
    actor: Actor,
    payload: BaseModel,
    accounts_service: AccountsService | None = None,
    goals_service: GoalsService | None = None,
) -> BaseModel:
    assert isinstance(payload, GoalProposalInput)
    accounts_svc = accounts_service or get_accounts_service()
    goals_svc = goals_service or get_goals_service()

    accounts = await accounts_svc.list_for_user(actor.subject_id())
    eligible = [account for account in accounts if account["kind"] != "invest"]
    if not eligible:
        return GoalProposalOutput(
            status="blocked",
            blockers=[
                ProposalBlocker(
                    code="no_eligible_accounts",
                    message="This customer holds no non-investment account to fund a goal from.",
                )
            ],
        )

    matches, _ = _resolve_ref(eligible, payload.account_ref)
    if len(matches) > 1 and payload.currency:
        named = payload.currency.strip().upper()
        narrowed = [account for account in matches if account["currency"] == named]
        if narrowed:
            matches = narrowed
    if not matches:
        return GoalProposalOutput(
            status="needs_clarification",
            candidates=[_to_balance(account) for account in eligible],
            blockers=[
                ProposalBlocker(
                    code="account_not_found",
                    message="No account of theirs matches that description.",
                )
            ],
        )
    if len(matches) > 1:
        return GoalProposalOutput(
            status="needs_clarification",
            candidates=[_to_balance(account) for account in matches],
            blockers=[
                ProposalBlocker(
                    code="account_ambiguous",
                    message="More than one of their accounts matches that description.",
                )
            ],
        )
    account = matches[0]

    today = datetime.now(timezone.utc).date()
    try:
        name = goals_validation.normalise_name(payload.name)
        target_minor = goals_validation.normalise_target_minor(payload.target_minor)
        target_date = goals_validation.normalise_target_date(payload.target_date, today)
    except ValidationError as exc:
        field = exc.details.get("field", "goal")
        return GoalProposalOutput(
            status="blocked",
            blockers=[ProposalBlocker(code=f"invalid_{field}", message=exc.message)],
        )

    active = await goals_svc.list_active_for_user(actor.subject_id())
    if any(goal.name.casefold() == name.casefold() for goal in active):
        return GoalProposalOutput(
            status="blocked",
            blockers=[
                ProposalBlocker(
                    code="duplicate_goal_name",
                    message=(
                        f"They already have an active goal called '{name}'. Ask them for a "
                        "different name, or pay into the existing goal instead."
                    ),
                )
            ],
        )

    days_remaining = max(1, (target_date - today).days)
    weeks_remaining = max(1, round(days_remaining / 7))
    months_remaining = max(1, round(days_remaining / 30.4375))
    suggested_monthly_minor = max(1, round(target_minor / (days_remaining / 30.4375)))
    suggested_weekly_minor = max(1, round(target_minor / (days_remaining / 7)))

    return GoalProposalOutput(
        status="proposed",
        proposalId=f"goal-{account['accountId'][:8]}-{target_minor}",
        accountId=account["accountId"],
        accountLabel=account["label"],
        currency=account["currency"],
        name=name,
        targetMinorUnits=target_minor,
        targetFormatted=format_minor(target_minor, account["currency"]),
        targetDate=target_date,
        daysRemaining=days_remaining,
        weeksRemaining=weeks_remaining,
        monthsRemaining=months_remaining,
        suggestedMonthlyMinorUnits=suggested_monthly_minor,
        suggestedMonthlyFormatted=format_minor(suggested_monthly_minor, account["currency"]),
        suggestedWeeklyMinorUnits=suggested_weekly_minor,
        suggestedWeeklyFormatted=format_minor(suggested_weekly_minor, account["currency"]),
        requiresHumanConfirmation=True,
    )


class StandingOrderProposalInput(BaseModel):
    goal_ref: str | None = Field(
        default=None,
        alias="goalRef",
        max_length=80,
        description=(
            "Which goal the standing order should feed, in the customer's own words: the goal's "
            "name or its id. Leave it out only when they have a single active goal."
        ),
    )
    amount_minor: int | None = Field(
        default=None,
        alias="amountMinorUnits",
        ge=1,
        description=(
            "The amount the customer asked to put aside each run, in integer minor units: "
            "370,00 RON is 37000. Leave it out to let GEMS size it from their required rate."
        ),
    )
    frequency: Literal["weekly", "monthly"] | None = Field(
        default=None, description="How often the money moves. Defaults to weekly."
    )
    model_config = {"populate_by_name": True}


class GoalOption(BaseModel):
    goal_id: str = Field(alias="goalId")
    name: str
    currency: str
    target_date: date = Field(alias="targetDate")
    model_config = {"populate_by_name": True}


class StandingOrderProposalOutput(BaseModel):
    status: Literal["proposed", "blocked", "needs_clarification"]
    proposal_kind: Literal["standingOrder"] = Field(default="standingOrder", alias="proposalKind")
    goal_id: str | None = Field(default=None, alias="goalId")
    goal_name: str | None = Field(default=None, alias="goalName")
    amount_minor: int | None = Field(default=None, alias="amountMinorUnits")
    amount_formatted: str | None = Field(default=None, alias="amountFormatted")
    frequency: Literal["weekly", "monthly"] | None = None
    currency: str | None = None
    requires_human_confirmation: bool = Field(default=True, alias="requiresHumanConfirmation")
    goals: list[GoalOption] = Field(default_factory=list)
    blockers: list[ProposalBlocker] = Field(default_factory=list)
    model_config = {"populate_by_name": True}


async def resolve_standing_order_proposal(
    actor: Actor,
    payload: BaseModel,
    goals_service: GoalsService | None = None,
) -> BaseModel:
    assert isinstance(payload, StandingOrderProposalInput)
    goals_svc = goals_service or get_goals_service()
    user_id = actor.subject_id()

    active = await goals_svc.list_active_for_user(user_id)
    if not active:
        return StandingOrderProposalOutput(
            status="blocked",
            blockers=[
                ProposalBlocker(
                    code="no_active_goal",
                    message="There is no active savings goal to attach a standing order to.",
                )
            ],
        )

    options = [
        GoalOption(
            goalId=candidate.id,
            name=candidate.name,
            currency=candidate.currency,
            targetDate=candidate.target_date,
        )
        for candidate in active
    ]
    matches = await goals_svc.match_active_for_user(user_id, payload.goal_ref)
    if not matches:
        return StandingOrderProposalOutput(
            status="needs_clarification",
            goals=options,
            blockers=[
                ProposalBlocker(
                    code="goal_not_found",
                    message="None of their active goals matches that description.",
                )
            ],
        )
    if len(matches) > 1:
        return StandingOrderProposalOutput(
            status="needs_clarification",
            goals=[
                GoalOption(
                    goalId=candidate.id,
                    name=candidate.name,
                    currency=candidate.currency,
                    targetDate=candidate.target_date,
                )
                for candidate in matches
            ],
            blockers=[
                ProposalBlocker(
                    code="goal_ambiguous",
                    message="They have more than one active goal. Ask which one this is for.",
                )
            ],
        )
    goal = matches[0]

    existing_order = await goals_svc.get_standing_order_for_goal(goal.id, user_id)
    if existing_order is not None:
        return StandingOrderProposalOutput(
            status="blocked",
            goalId=goal.id,
            goalName=goal.name,
            blockers=[
                ProposalBlocker(
                    code="already_has_standing_order",
                    message="This goal already has an open standing order.",
                )
            ],
        )

    frequency: Literal["weekly", "monthly"] = payload.frequency or "weekly"

    pace = await analytics_capabilities.resolve_goal_pace(
        actor, analytics_capabilities.GoalPaceInput(goalId=goal.id)
    )
    assert isinstance(pace, analytics_capabilities.GoalPaceOutput)

    if pace.status == "completed":
        return StandingOrderProposalOutput(
            status="blocked",
            goalId=goal.id,
            goalName=goal.name,
            blockers=[
                ProposalBlocker(
                    code="goal_already_completed",
                    message="This goal has already reached its target.",
                )
            ],
        )

    amount = payload.amount_minor
    if amount is None and frequency == "monthly":
        gap = await analytics_capabilities.resolve_goal_gap(
            actor, analytics_capabilities.GoalGapInput(goalId=goal.id)
        )
        assert isinstance(gap, analytics_capabilities.GoalGapOutput)
        amount = gap.required_minor_per_month
    elif amount is None:
        amount = pace.required_weekly_rate_minor

    if amount is None or amount <= 0:
        return StandingOrderProposalOutput(
            status="blocked",
            goalId=goal.id,
            goalName=goal.name,
            blockers=[
                ProposalBlocker(
                    code="no_rate_available",
                    message=(
                        "GEMS could not work out a rate for this goal. Ask them how much they "
                        "want to put aside each time."
                    ),
                )
            ],
        )

    return StandingOrderProposalOutput(
        status="proposed",
        goalId=goal.id,
        goalName=goal.name,
        amountMinorUnits=amount,
        amountFormatted=format_minor(amount, goal.currency),
        frequency=frequency,
        currency=goal.currency,
        requiresHumanConfirmation=True,
    )
