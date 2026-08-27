from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

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

    existing = await goals_svc.get_for_user(actor.subject_id())
    if existing is not None:
        return GoalProposalOutput(
            status="blocked",
            blockers=[
                ProposalBlocker(
                    code="already_has_goal",
                    message=(
                        f"There is already an active goal, '{existing.name}'. GEMS supports one "
                        "active goal per user for now."
                    ),
                )
            ],
        )

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
        requiresHumanConfirmation=True,
    )


class StandingOrderProposalInput(BaseModel):
    pass


class StandingOrderProposalOutput(BaseModel):
    status: Literal["proposed", "blocked"]
    proposal_kind: Literal["standingOrder"] = Field(default="standingOrder", alias="proposalKind")
    goal_id: str | None = Field(default=None, alias="goalId")
    goal_name: str | None = Field(default=None, alias="goalName")
    amount_minor: int | None = Field(default=None, alias="amountMinorUnits")
    amount_formatted: str | None = Field(default=None, alias="amountFormatted")
    frequency: Literal["weekly", "monthly"] | None = None
    currency: str | None = None
    requires_human_confirmation: bool = Field(default=True, alias="requiresHumanConfirmation")
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

    goal = await goals_svc.get_for_user(user_id)
    if goal is None:
        return StandingOrderProposalOutput(
            status="blocked",
            blockers=[
                ProposalBlocker(
                    code="no_active_goal",
                    message="There is no active savings goal to attach a standing order to.",
                )
            ],
        )

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

    pace = await analytics_capabilities.resolve_goal_pace(
        actor, analytics_capabilities.GoalPaceInput()
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
    if pace.required_weekly_rate_minor is None:
        return StandingOrderProposalOutput(
            status="blocked",
            goalId=goal.id,
            goalName=goal.name,
            blockers=[
                ProposalBlocker(
                    code="no_rate_available",
                    message="GEMS could not work out a required weekly rate for this goal.",
                )
            ],
        )

    amount = pace.required_weekly_rate_minor
    return StandingOrderProposalOutput(
        status="proposed",
        goalId=goal.id,
        goalName=goal.name,
        amountMinorUnits=amount,
        amountFormatted=format_minor(amount, goal.currency),
        frequency="weekly",
        currency=goal.currency,
        requiresHumanConfirmation=True,
    )
