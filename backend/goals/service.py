import calendar
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, ClassVar, Literal, Protocol

from motor.motor_asyncio import AsyncIOMotorClientSession
from pydantic import BaseModel, Field

from backend.accounts.account import AccountKind
from backend.accounts.service import AccountsService, get_accounts_service
from backend.command_bus import Command, CommandBus, CommandResult, bus
from backend.database.records import AuditRecord, DomainEvent
from backend.database.repositories import (
    MongoAuthUserRepository,
    MongoGoalInviteRepository,
    MongoGoalRepository,
    MongoStandingOrderRepository,
)
from backend.goals import validation
from backend.goals.goal import ContributionShare, Goal
from backend.goals.invite import GoalInvite, GoalInviteStatus
from backend.goals.standing_order import StandingOrder
from backend.goals.streak import STREAK_LOOKBACK_WEEKS, streak_from_movements
from backend.helpers.context import Actor, ActorContext
from backend.helpers.errors import (
    ConflictError,
    IllegalTransitionError,
    NotFoundError,
    ValidationError,
)
from backend.ledger.service import LedgerService, get_ledger_service

__all__ = [
    "Goal",
    "GoalInvite",
    "GoalProgress",
    "GoalsService",
    "StandingOrder",
    "get_goals_service",
]

logger = logging.getLogger(__name__)


class GoalRepository(Protocol):
    async def add(
        self, goal: Goal, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def get(self, goal_id: str) -> Goal | None: ...

    async def get_for_user(self, user_id: str) -> Goal | None: ...

    async def list_active_for_user(self, user_id: str) -> list[Goal]: ...

    async def set_streak(
        self,
        goal_id: str,
        streak_weeks: int,
        streak_last_week: str | None,
        computed_at: datetime,
        session: AsyncIOMotorClientSession | None = None,
    ) -> None: ...

    async def close(
        self,
        goal_id: str,
        user_id: str,
        closed_at: datetime,
        session: AsyncIOMotorClientSession | None = None,
    ) -> bool: ...

    async def mark_achieved(
        self,
        goal_id: str,
        achieved_at: datetime,
        session: AsyncIOMotorClientSession | None = None,
    ) -> bool: ...

    async def add_member(
        self,
        goal_id: str,
        user_id: str,
        share: ContributionShare | None,
        session: AsyncIOMotorClientSession | None = None,
    ) -> bool: ...

    async def add_contribution(
        self,
        goal_id: str,
        user_id: str,
        amount_minor: int,
        session: AsyncIOMotorClientSession | None = None,
    ) -> None: ...


class GoalInviteRepository(Protocol):
    async def add(
        self, invite: GoalInvite, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def get(self, invite_id: str) -> GoalInvite | None: ...

    async def list_for_goal(self, goal_id: str) -> list[GoalInvite]: ...

    async def set_status(
        self,
        invite_id: str,
        status: GoalInviteStatus,
        responded_at: datetime,
        session: AsyncIOMotorClientSession | None = None,
    ) -> bool: ...


class ResolvedUsername(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def username(self) -> str: ...

    @property
    def display_name(self) -> str: ...


class UsernameDirectory(Protocol):
    async def get_by_username(self, username: str) -> ResolvedUsername | None: ...

    async def get(self, user_id: str) -> ResolvedUsername | None: ...


class StandingOrderRepository(Protocol):
    async def add(
        self, order: StandingOrder, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def get(self, order_id: str) -> StandingOrder | None: ...

    async def get_open_for_goal(self, goal_id: str) -> StandingOrder | None: ...

    async def get_open_for_goal_and_source(
        self, goal_id: str, source_account_id: str
    ) -> StandingOrder | None: ...

    async def list_open_for_goal(self, goal_id: str) -> list[StandingOrder]: ...

    async def list_due(self, now: datetime, limit: int = 200) -> list[StandingOrder]: ...

    async def set_status(
        self,
        order_id: str,
        user_id: str,
        status: str,
        session: AsyncIOMotorClientSession | None = None,
    ) -> bool: ...

    async def set_amount(
        self,
        order_id: str,
        user_id: str,
        amount_minor: int,
        session: AsyncIOMotorClientSession | None = None,
    ) -> bool: ...

    async def update_details(
        self,
        order_id: str,
        user_id: str,
        *,
        source_account_id: str | None = None,
        amount_minor: int | None = None,
        frequency: str | None = None,
        session: AsyncIOMotorClientSession | None = None,
    ) -> bool: ...

    async def record_run(
        self,
        order_id: str,
        next_run_at: datetime,
        ran_at: datetime,
        session: AsyncIOMotorClientSession | None = None,
    ) -> None: ...

    async def record_failure(
        self,
        order_id: str,
        reason: str,
        failed_at: datetime,
        session: AsyncIOMotorClientSession | None = None,
    ) -> None: ...


class Clock(Protocol):
    def today(self) -> date: ...

    def now(self) -> datetime: ...


class SystemClock:
    def today(self) -> date:
        return datetime.now(timezone.utc).date()

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(slots=True, frozen=True)
class GoalProgress:
    goal: Goal
    progress_minor: int
    streak_weeks: int = 0
    streak_last_week: str | None = None


def _advance(when: datetime, frequency: str) -> datetime:
    if frequency == "weekly":
        return when + timedelta(days=7)
    month_index = when.month  # advance exactly one month
    year = when.year + month_index // 12
    month = month_index % 12 + 1
    day = min(when.day, calendar.monthrange(year, month)[1])
    return when.replace(year=year, month=month, day=day)


class CollaboratorInput(BaseModel):
    username: str
    share_kind: Literal["fixed", "percent"]
    amount_minor: int | None = None
    percent_bp: int | None = None


class CreateGoal(Command):
    command_name: ClassVar[str] = "goals.create"

    parent_account_id: str
    name: str
    target_minor: int
    target_date: date
    initial_deposit_minor: int = Field(default=0, ge=0)
    collaborators: list[CollaboratorInput] = Field(default_factory=list)


class CloseGoal(Command):
    command_name: ClassVar[str] = "goals.close"

    goal_id: str


class DepositToGoal(Command):
    command_name: ClassVar[str] = "goals.deposit"

    goal_id: str
    amount_minor: int
    source_account_id: str | None = None


class WithdrawFromGoal(Command):
    command_name: ClassVar[str] = "goals.withdraw"

    goal_id: str
    amount_minor: int


class CreateStandingOrder(Command):
    command_name: ClassVar[str] = "goals.standing_order.create"

    goal_id: str
    amount_minor: int
    frequency: str
    source_account_id: str | None = None
    created_via: Literal["user", "agent-suggestion-confirmed"] = "user"


class UpdateStandingOrder(Command):
    command_name: ClassVar[str] = "goals.standing_order.update"

    standing_order_id: str
    source_account_id: str | None = None
    amount_minor: int | None = None
    frequency: str | None = None


class UpdateStandingOrderAmount(Command):
    command_name: ClassVar[str] = "goals.standing_order.update_amount"

    standing_order_id: str
    amount_minor: int


class PauseStandingOrder(Command):
    command_name: ClassVar[str] = "goals.standing_order.pause"

    standing_order_id: str


class ResumeStandingOrder(Command):
    command_name: ClassVar[str] = "goals.standing_order.resume"

    standing_order_id: str


class CancelStandingOrder(Command):
    command_name: ClassVar[str] = "goals.standing_order.cancel"

    standing_order_id: str


class RunStandingOrder(Command):
    command_name: ClassVar[str] = "goals.standing_order.run"

    standing_order_id: str


class RespondToGoalInvite(Command):
    command_name: ClassVar[str] = "goals.invite.respond"

    invite_id: str
    accept: bool


class GoalsService:
    def __init__(
        self,
        goals: GoalRepository,
        standing_orders: StandingOrderRepository,
        invites: GoalInviteRepository,
        accounts: AccountsService,
        ledger: LedgerService,
        users: UsernameDirectory,
        clock: Clock,
    ) -> None:
        self._goals = goals
        self._standing_orders = standing_orders
        self._invites = invites
        self._accounts = accounts
        self._ledger = ledger
        self._users = users
        self._clock = clock

    def register(self, command_bus: CommandBus) -> None:
        command_bus.register(CreateGoal, self._handle_create)
        command_bus.register(CloseGoal, self._handle_close)
        command_bus.register(DepositToGoal, self._handle_deposit)
        command_bus.register(WithdrawFromGoal, self._handle_withdraw)
        command_bus.register(CreateStandingOrder, self._handle_create_standing_order)
        command_bus.register(UpdateStandingOrder, self._handle_update_standing_order)
        command_bus.register(UpdateStandingOrderAmount, self._handle_update_standing_order)
        command_bus.register(PauseStandingOrder, self._handle_pause_standing_order)
        command_bus.register(ResumeStandingOrder, self._handle_resume_standing_order)
        command_bus.register(CancelStandingOrder, self._handle_cancel_standing_order)
        command_bus.register(RunStandingOrder, self._handle_run_standing_order)
        command_bus.register(RespondToGoalInvite, self._handle_respond_to_invite)

    async def get_for_user(self, user_id: str) -> Goal | None:
        return await self._goals.get_for_user(user_id)

    async def list_active_for_user(self, user_id: str) -> list[Goal]:
        return await self._goals.list_active_for_user(user_id)

    async def match_active_for_user(self, user_id: str, ref: str | None) -> list[Goal]:
        goals = await self._goals.list_active_for_user(user_id)
        needle = (ref or "").strip()
        if not needle:
            return goals
        by_id = [goal for goal in goals if goal.id == needle]
        if by_id:
            return by_id
        folded = needle.casefold()
        exact = [goal for goal in goals if goal.name.casefold() == folded]
        if exact:
            return exact
        return [goal for goal in goals if folded in goal.name.casefold()]

    async def _derive_streak(self, goal: Goal) -> tuple[int, str | None]:
        now = self._clock.now()
        movements = await self._ledger.statement_movements(
            goal.account_id, now - timedelta(weeks=STREAK_LOOKBACK_WEEKS), now
        )
        return streak_from_movements(movements, now)

    async def _progress_of(self, goal: Goal, user_id: str) -> GoalProgress:
        account = await self._accounts.get_owned(goal.account_id, user_id)
        balances = await self._ledger.balances_of([account.id])
        streak_weeks, streak_last_week = await self._derive_streak(goal)
        return GoalProgress(
            goal=goal,
            progress_minor=balances.get(account.id, 0),
            streak_weeks=streak_weeks,
            streak_last_week=streak_last_week,
        )

    async def get_progress_for_user(self, user_id: str) -> GoalProgress | None:
        goal = await self._goals.get_for_user(user_id)
        if goal is None:
            return None
        return await self._progress_of(goal, user_id)

    async def list_active_progress_for_user(self, user_id: str) -> list[GoalProgress]:
        goals = await self._goals.list_active_for_user(user_id)
        return [await self._progress_of(goal, user_id) for goal in goals]

    async def get_progress_for_goal(self, goal_id: str, user_id: str) -> GoalProgress:
        goal = await self._goals.get(goal_id)
        if goal is None or not goal.is_owned_by(user_id):
            raise NotFoundError(
                "That goal does not belong to you.", details={"field": "goalId"}
            )
        return await self._progress_of(goal, user_id)

    async def collaborators_view(self, goal: Goal) -> list[dict[str, Any]]:
        member_ids = [goal.user_id, *goal.member_ids]
        shares = {share.user_id: share for share in goal.contribution_plan}
        view = []
        for member_id in member_ids:
            user = await self._users.get(member_id)
            share = shares.get(member_id)
            view.append(
                {
                    "userId": member_id,
                    "displayName": user.display_name if user is not None else member_id,
                    "isCreator": member_id == goal.user_id,
                    "share": share.public_view() if share is not None else None,
                    "contributedMinorUnits": goal.contributions_minor.get(member_id, 0),
                }
            )
        return view

    async def pending_invites_view(self, goal_id: str) -> list[dict[str, Any]]:
        invites = await self._invites.list_for_goal(goal_id)
        return [
            invite.public_view()
            for invite in invites
            if invite.status is GoalInviteStatus.PENDING
        ]

    async def _persist_streak(
        self, goal: Goal, session: AsyncIOMotorClientSession | None = None
    ) -> tuple[int, str | None]:
        streak_weeks, streak_last_week = await self._derive_streak(goal)
        await self._goals.set_streak(
            goal.id, streak_weeks, streak_last_week, self._clock.now(), session=session
        )
        return streak_weeks, streak_last_week

    async def get_standing_order_for_goal(
        self, goal_id: str, user_id: str
    ) -> StandingOrder | None:
        goal = await self._goals.get(goal_id)
        if goal is None or goal.user_id != user_id:
            raise NotFoundError(
                "That goal does not belong to you.", details={"field": "goalId"}
            )
        return await self._standing_orders.get_open_for_goal(goal.id)

    async def get_standing_orders_for_goal(
        self, goal_id: str, user_id: str
    ) -> list[StandingOrder]:
        goal = await self._goals.get(goal_id)
        if goal is None or goal.user_id != user_id:
            raise NotFoundError(
                "That goal does not belong to you.", details={"field": "goalId"}
            )
        if hasattr(self._standing_orders, "list_open_for_goal"):
            return await self._standing_orders.list_open_for_goal(goal.id)
        open_one = await self._standing_orders.get_open_for_goal(goal.id)
        return [open_one] if open_one else []

    async def _handle_create(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, CreateGoal)
        user_id = context.actor.subject_id()
        parent = await self._accounts.get_owned(command.parent_account_id, user_id)
        parent.guard_can_send()
        today = self._clock.today()
        name = validation.normalise_name(command.name)
        target_minor = validation.normalise_target_minor(command.target_minor)
        target_date = validation.normalise_target_date(command.target_date, today)

        validation.normalise_collaborator_count(len(command.collaborators))
        inviter = await self._users.get(user_id)
        inviter_name = inviter.display_name if inviter is not None else user_id
        seen_usernames: set[str] = set()
        resolved_collaborators: list[
            tuple[ResolvedUsername, Literal["fixed", "percent"], int | None, int | None]
        ] = []
        for collaborator in command.collaborators:
            username = validation.normalise_username_for_invite(collaborator.username)
            if username in seen_usernames:
                raise ValidationError(
                    "Each collaborator can only be invited once.",
                    details={"field": "username", "username": username},
                )
            seen_usernames.add(username)
            resolved = await self._users.get_by_username(username)
            if resolved is None:
                raise ValidationError(
                    "There is no GEMS customer with that username.",
                    details={"field": "username", "username": username},
                )
            if resolved.id == user_id:
                raise ValidationError(
                    "You can't invite yourself to your own goal.",
                    details={"field": "username", "username": username},
                )
            amount_minor, percent_bp = validation.normalise_share(
                collaborator.share_kind, collaborator.amount_minor, collaborator.percent_bp
            )
            resolved_collaborators.append((resolved, collaborator.share_kind, amount_minor, percent_bp))

        pot = await self._accounts.open_account(
            user_id=user_id,
            holder_name=parent.holder_name,
            currency=parent.currency,
            kind=AccountKind.JOINT if resolved_collaborators else AccountKind.SAVINGS,
            label=name,
            owner_ids=[user_id] if resolved_collaborators else None,
            session=session,
        )

        goal = Goal(
            user_id=user_id,
            account_id=pot.id,
            parent_account_id=parent.id,
            name=name,
            target_minor=target_minor,
            currency=parent.currency,
            target_date=target_date,
            contribution_plan=[
                ContributionShare(
                    user_id=resolved.id,
                    kind=share_kind,
                    amount_minor=amount_minor,
                    percent_bp=percent_bp,
                )
                for resolved, share_kind, amount_minor, percent_bp in resolved_collaborators
            ],
        )
        await self._goals.add(goal, session=session)

        invite_events: list[DomainEvent] = []
        for resolved, share_kind, amount_minor, percent_bp in resolved_collaborators:
            invite = GoalInvite(
                goal_id=goal.id,
                goal_name=goal.name,
                currency=goal.currency,
                inviter_id=user_id,
                inviter_name=inviter_name,
                invitee_id=resolved.id,
                invitee_username=resolved.username,
                share_kind=share_kind,
                share_amount_minor=amount_minor,
                share_percent_bp=percent_bp,
            )
            await self._invites.add(invite, session=session)
            invite_events.append(
                DomainEvent(
                    name="goals.invite_sent",
                    aggregate_type="goalInvite",
                    aggregate_id=invite.id,
                    payload={"userId": invite.invitee_id} | invite.public_view(),
                )
            )

        if command.initial_deposit_minor > 0:
            amount = validation.normalise_movement_minor(
                command.initial_deposit_minor, "initialDepositMinorUnits"
            )
            balance = await self._ledger.balance_of(parent.id)
            parent.guard_sufficient(balance, amount)
            await self._ledger.transfer(
                source_account_id=parent.id,
                target_account_id=pot.id,
                amount_minor=amount,
                currency=parent.currency,
                reference="Initial savings deposit",
                counterparty=name,
                category="savings",
                correlation_id=context.correlation_id,
                actor=context.actor.label(),
                session=session,
            )
            await self._goals.add_contribution(goal.id, user_id, amount, session=session)

        return CommandResult(
            data=goal.public_view() | {"invitesSent": len(invite_events)},
            audit=AuditRecord(
                action="goals.created",
                entity_type="goal",
                entity_id=goal.id,
                after=goal.public_view(),
            ),
            events=[
                DomainEvent(name="goals.created", aggregate_type="goal", aggregate_id=goal.id),
                *invite_events,
            ],
        )

    async def _load_active_owned_goal(self, goal_id: str, user_id: str) -> Goal:
        goal = await self._goals.get(goal_id)
        if goal is None or goal.user_id != user_id:
            raise NotFoundError(
                "That goal does not belong to you.", details={"field": "goalId"}
            )
        if goal.status != "active":
            raise IllegalTransitionError(
                "That goal is already closed.", details={"field": "goalId"}
            )
        return goal

    async def _load_active_goal_for_deposit(self, goal_id: str, user_id: str) -> Goal:
        goal = await self._goals.get(goal_id)
        if goal is None or not goal.is_owned_by(user_id):
            raise NotFoundError(
                "That goal does not belong to you.", details={"field": "goalId"}
            )
        if goal.status != "active":
            raise IllegalTransitionError(
                "That goal is already closed.", details={"field": "goalId"}
            )
        return goal

    async def _maybe_achieve(
        self,
        goal: Goal,
        balance_before: int,
        amount: int,
        session: AsyncIOMotorClientSession | None,
    ) -> list[DomainEvent]:
        if goal.achieved_at is not None:
            return []
        if balance_before >= goal.target_minor or balance_before + amount < goal.target_minor:
            return []
        achieved_at = self._clock.now()
        if not await self._goals.mark_achieved(goal.id, achieved_at, session=session):
            return []
        payload = {
            "name": goal.name,
            "targetMinorUnits": goal.target_minor,
            "currency": goal.currency,
        }
        return [
            DomainEvent(
                name="goals.achieved",
                aggregate_type="goal",
                aggregate_id=goal.id,
                payload={"userId": member_id} | payload,
            )
            for member_id in [goal.user_id, *goal.member_ids]
        ]

    async def _handle_deposit(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, DepositToGoal)
        user_id = context.actor.subject_id()
        goal = await self._load_active_goal_for_deposit(command.goal_id, user_id)
        amount = validation.normalise_movement_minor(command.amount_minor, "amountMinorUnits")

        source_account_id = command.source_account_id
        if source_account_id is None:
            if user_id != goal.user_id:
                raise ValidationError(
                    "Choose which of your own accounts to contribute from.",
                    details={"field": "sourceAccountId"},
                )
            source_account_id = goal.parent_account_id

        source = await self._accounts.get_owned(source_account_id, user_id)
        source.guard_can_send()
        if source.currency != goal.currency:
            raise ValidationError(
                "The funding account must be in the same currency as the goal.",
                details={"field": "sourceAccountId"},
            )
        pot = await self._accounts.get_owned(goal.account_id, user_id)
        pot.guard_can_receive()

        source_balance = await self._ledger.balance_of(source.id)
        source.guard_sufficient(source_balance, amount)
        pot_balance = await self._ledger.balance_of(pot.id)

        transaction = await self._ledger.transfer(
            source_account_id=source.id,
            target_account_id=pot.id,
            amount_minor=amount,
            currency=goal.currency,
            reference="Savings deposit",
            counterparty=goal.name,
            category="savings",
            correlation_id=context.correlation_id,
            actor=context.actor.label(),
            session=session,
        )
        await self._goals.add_contribution(goal.id, user_id, amount, session=session)

        streak_weeks, streak_last_week = await self._persist_streak(goal, session=session)
        achievements = await self._maybe_achieve(goal, pot_balance, amount, session)
        after = {
            "progressMinorUnits": pot_balance + amount,
            "journalTransactionId": transaction.id,
            "streakWeeks": streak_weeks,
            "streakLastWeek": streak_last_week,
        }
        if achievements:
            after = after | {"achieved": True}
        events = [
            DomainEvent(
                name="goals.deposited",
                aggregate_type="goal",
                aggregate_id=goal.id,
                payload=after,
            ),
            *achievements,
        ]
        return CommandResult(
            data=goal.public_view() | after,
            audit=AuditRecord(
                action="goals.deposited",
                entity_type="goal",
                entity_id=goal.id,
                after=after,
            ),
            events=events,
        )

    async def _handle_withdraw(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, WithdrawFromGoal)
        user_id = context.actor.subject_id()
        goal = await self._load_active_owned_goal(command.goal_id, user_id)
        amount = validation.normalise_movement_minor(command.amount_minor, "amountMinorUnits")

        pot = await self._accounts.get_owned(goal.account_id, user_id)
        pot.guard_can_send()
        parent = await self._accounts.get_owned(goal.parent_account_id, user_id)
        parent.guard_can_receive()

        pot_balance = await self._ledger.balance_of(pot.id)
        pot.guard_sufficient(pot_balance, amount)

        transaction = await self._ledger.transfer(
            source_account_id=pot.id,
            target_account_id=parent.id,
            amount_minor=amount,
            currency=goal.currency,
            reference="Savings withdrawal",
            counterparty=parent.label,
            category="savings",
            correlation_id=context.correlation_id,
            actor=context.actor.label(),
            session=session,
        )

        streak_weeks, streak_last_week = await self._persist_streak(goal, session=session)
        after = {
            "progressMinorUnits": pot_balance - amount,
            "journalTransactionId": transaction.id,
            "streakWeeks": streak_weeks,
            "streakLastWeek": streak_last_week,
        }
        return CommandResult(
            data=goal.public_view() | after,
            audit=AuditRecord(
                action="goals.withdrawn",
                entity_type="goal",
                entity_id=goal.id,
                after=after,
            ),
            events=[
                DomainEvent(
                    name="goals.withdrawn",
                    aggregate_type="goal",
                    aggregate_id=goal.id,
                    payload=after,
                )
            ],
        )

    async def _handle_close(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, CloseGoal)
        user_id = context.actor.subject_id()

        goal = await self._goals.get(command.goal_id)
        if goal is None or goal.user_id != user_id:
            raise NotFoundError(
                "That goal does not belong to you.", details={"field": "goalId"}
            )
        if goal.status != "active":
            raise IllegalTransitionError(
                "That goal is already closed.", details={"field": "goalId"}
            )

        pot = await self._accounts.get_owned(goal.account_id, user_id)
        parent = await self._accounts.get_owned(goal.parent_account_id, user_id)
        swept_minor = 0
        shares_parent_account = goal.uses_shared_parent_account()
        if not shares_parent_account:
            pot_balance = await self._ledger.balance_of(pot.id)
            if pot_balance > 0:
                pot.guard_can_send()
                await self._ledger.transfer(
                    source_account_id=pot.id,
                    target_account_id=parent.id,
                    amount_minor=pot_balance,
                    currency=goal.currency,
                    reference="Savings pot closed — balance returned",
                    counterparty=parent.label,
                    category="savings",
                    correlation_id=context.correlation_id,
                    actor=context.actor.label(),
                    session=session,
                )
                swept_minor = pot_balance

            await self._accounts.close_owned(pot.id, user_id, session=session)

        open_order = await self._standing_orders.get_open_for_goal(goal.id)
        if open_order is not None:
            await self._standing_orders.set_status(
                open_order.id, user_id, "cancelled", session=session
            )

        closed_at = datetime.now(timezone.utc)
        closed = await self._goals.close(goal.id, user_id, closed_at, session=session)
        if not closed:
            raise IllegalTransitionError(
                "That goal is already closed.", details={"field": "goalId"}
            )

        before = goal.public_view()
        after = before | {
            "status": "closed",
            "sweptBackMinorUnits": swept_minor,
            "sharedParentAccount": shares_parent_account,
        }
        return CommandResult(
            data=after,
            audit=AuditRecord(
                action="goals.closed",
                entity_type="goal",
                entity_id=goal.id,
                before=before,
                after=after,
            ),
            events=[
                DomainEvent(name="goals.closed", aggregate_type="goal", aggregate_id=goal.id)
            ],
        )

    async def _handle_create_standing_order(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, CreateStandingOrder)
        user_id = context.actor.subject_id()
        goal = await self._load_active_owned_goal(command.goal_id, user_id)

        source = await self._accounts.get_owned(
            command.source_account_id or goal.parent_account_id, user_id
        )
        source.guard_can_send()
        if source.currency != goal.currency:
            raise ValidationError(
                "The funding account must be in the same currency as the goal.",
                details={"field": "sourceAccountId"},
            )

        if hasattr(self._standing_orders, "get_open_for_goal_and_source"):
            existing = await self._standing_orders.get_open_for_goal_and_source(goal.id, source.id)
        else:
            open_order = await self._standing_orders.get_open_for_goal(goal.id)
            existing = open_order if open_order and open_order.source_account_id == source.id else None

        if existing is not None:
            raise ConflictError(
                "This account already has an open standing order for this goal.",
                details={"field": "sourceAccountId", "existingStandingOrderId": existing.id},
            )

        amount = validation.normalise_movement_minor(command.amount_minor, "amountMinorUnits")
        frequency = validation.normalise_frequency(command.frequency)

        order = StandingOrder(
            goal_id=goal.id,
            user_id=user_id,
            source_account_id=source.id,
            target_account_id=goal.account_id,
            amount_minor=amount,
            currency=goal.currency,
            frequency=frequency,
            next_run_at=_advance(self._clock.now(), frequency),
            created_via=command.created_via,
        )
        await self._standing_orders.add(order, session=session)

        return CommandResult(
            data=order.public_view(),
            audit=AuditRecord(
                action="goals.standing_order.created",
                entity_type="standingOrder",
                entity_id=order.id,
                after=order.public_view(),
            ),
            events=[
                DomainEvent(
                    name="goals.standing_order.created",
                    aggregate_type="standingOrder",
                    aggregate_id=order.id,
                )
            ],
        )

    async def _handle_update_standing_order(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, (UpdateStandingOrder, UpdateStandingOrderAmount))
        user_id = context.actor.subject_id()
        order = await self._standing_orders.get(command.standing_order_id)
        if order is None or order.user_id != user_id:
            raise NotFoundError(
                "That standing order does not belong to you.",
                details={"field": "standingOrderId"},
            )

        source_id = getattr(command, "source_account_id", None)
        if source_id is not None and source_id != order.source_account_id:
            source = await self._accounts.get_owned(source_id, user_id)
            source.guard_can_send()
            if source.currency != order.currency:
                raise ValidationError(
                    "The funding account must be in the same currency as the goal.",
                    details={"field": "sourceAccountId"},
                )

        amount = None
        if command.amount_minor is not None:
            amount = validation.normalise_movement_minor(command.amount_minor, "amountMinorUnits")

        frequency = None
        freq_val = getattr(command, "frequency", None)
        if freq_val is not None:
            frequency = validation.normalise_frequency(freq_val)

        if hasattr(self._standing_orders, "update_details"):
            changed = await self._standing_orders.update_details(
                order.id,
                user_id,
                source_account_id=source_id,
                amount_minor=amount,
                frequency=frequency,
                session=session,
            )
        else:
            changed = True
            if amount is not None:
                changed = await self._standing_orders.set_amount(order.id, user_id, amount, session=session)

        if not changed:
            raise IllegalTransitionError(
                "That standing order can no longer be changed.",
                details={"field": "standingOrderId", "status": order.status},
            )
        before = order.public_view()
        updated_order = await self._standing_orders.get(order.id)
        after = updated_order.public_view() if updated_order else before
        return CommandResult(
            data=after,
            audit=AuditRecord(
                action="goals.standing_order.updated",
                entity_type="standingOrder",
                entity_id=order.id,
                before=before,
                after=after,
            ),
            events=[
                DomainEvent(
                    name="goals.standing_order.updated",
                    aggregate_type="standingOrder",
                    aggregate_id=order.id,
                )
            ],
        )

    _handle_update_standing_order_amount = _handle_update_standing_order

    async def _transition_standing_order(
        self,
        standing_order_id: str,
        context: ActorContext,
        session: AsyncIOMotorClientSession,
        new_status: str,
        action: str,
    ) -> CommandResult:
        user_id = context.actor.subject_id()
        order = await self._standing_orders.get(standing_order_id)
        if order is None or order.user_id != user_id:
            raise NotFoundError(
                "That standing order does not belong to you.",
                details={"field": "standingOrderId"},
            )
        changed = await self._standing_orders.set_status(
            order.id, user_id, new_status, session=session
        )
        if not changed:
            raise IllegalTransitionError(
                "That standing order can no longer be changed.",
                details={"field": "standingOrderId", "status": order.status},
            )
        after = order.public_view() | {"status": new_status}
        return CommandResult(
            data=after,
            audit=AuditRecord(
                action=action,
                entity_type="standingOrder",
                entity_id=order.id,
                before=order.public_view(),
                after=after,
            ),
        )

    async def _handle_pause_standing_order(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, PauseStandingOrder)
        return await self._transition_standing_order(
            command.standing_order_id, context, session, "paused", "goals.standing_order.paused"
        )

    async def _handle_resume_standing_order(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, ResumeStandingOrder)
        return await self._transition_standing_order(
            command.standing_order_id, context, session, "active", "goals.standing_order.resumed"
        )

    async def _handle_cancel_standing_order(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, CancelStandingOrder)
        return await self._transition_standing_order(
            command.standing_order_id,
            context,
            session,
            "cancelled",
            "goals.standing_order.cancelled",
        )

    async def _handle_run_standing_order(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, RunStandingOrder)
        order = await self._standing_orders.get(command.standing_order_id)
        if order is None or order.status != "active":
            return CommandResult(
                data={"status": "skipped", "reason": "not_active"},
                audit=AuditRecord(
                    action="goals.standing_order.skipped",
                    entity_type="standingOrder",
                    entity_id=command.standing_order_id,
                    after={"reason": "not_active"},
                ),
            )

        now = self._clock.now()
        source = await self._accounts.get_owned(order.source_account_id, order.user_id)
        target = await self._accounts.get_owned(order.target_account_id, order.user_id)

        if source.status.value != "active":
            await self._standing_orders.record_failure(
                order.id, "source_account_inactive", now, session=session
            )
            return CommandResult(
                data={"status": "skipped", "reason": "source_account_inactive"},
                audit=AuditRecord(
                    action="goals.standing_order.skipped",
                    entity_type="standingOrder",
                    entity_id=order.id,
                    after={"reason": "source_account_inactive"},
                ),
            )

        balance = await self._ledger.balance_of(source.id)
        if balance < order.amount_minor:
            await self._standing_orders.record_failure(
                order.id, "insufficient_funds", now, session=session
            )
            return CommandResult(
                data={"status": "skipped", "reason": "insufficient_funds"},
                audit=AuditRecord(
                    action="goals.standing_order.skipped",
                    entity_type="standingOrder",
                    entity_id=order.id,
                    after={"reason": "insufficient_funds"},
                ),
            )

        target_balance = await self._ledger.balance_of(target.id)
        transaction = await self._ledger.transfer(
            source_account_id=source.id,
            target_account_id=target.id,
            amount_minor=order.amount_minor,
            currency=order.currency,
            reference="Standing order",
            counterparty=target.label,
            category="savings",
            correlation_id=context.correlation_id,
            actor=context.actor.label(),
            session=session,
        )
        next_run_at = _advance(order.next_run_at, order.frequency)
        await self._standing_orders.record_run(order.id, next_run_at, now, session=session)

        goal = await self._goals.get(order.goal_id)
        achievements: list[DomainEvent] = []
        if goal is not None:
            await self._goals.add_contribution(
                goal.id, order.user_id, order.amount_minor, session=session
            )
            await self._persist_streak(goal, session=session)
            achievements = await self._maybe_achieve(
                goal, target_balance, order.amount_minor, session
            )

        after = {
            "journalTransactionId": transaction.id,
            "amountMinorUnits": order.amount_minor,
            "nextRunAt": next_run_at.isoformat(),
        }
        events = [
            DomainEvent(
                name="goals.standing_order.executed",
                aggregate_type="standingOrder",
                aggregate_id=order.id,
                payload=after,
            ),
            *achievements,
        ]
        return CommandResult(
            data={"status": "executed"} | after,
            audit=AuditRecord(
                action="goals.standing_order.executed",
                entity_type="standingOrder",
                entity_id=order.id,
                after=after,
            ),
            events=events,
        )

    async def _handle_respond_to_invite(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, RespondToGoalInvite)
        user_id = context.actor.subject_id()
        invite = await self._invites.get(command.invite_id)
        if invite is None or invite.invitee_id != user_id:
            raise NotFoundError(
                "That invitation does not belong to you.", details={"field": "inviteId"}
            )
        invite.guard_pending()

        if command.accept:
            goal = await self._goals.get(invite.goal_id)
            if goal is None or goal.status != "active":
                raise IllegalTransitionError(
                    "That goal is no longer active.", details={"field": "inviteId"}
                )
            share = None
            if invite.share_amount_minor is not None or invite.share_percent_bp is not None:
                share = ContributionShare(
                    user_id=user_id,
                    kind=invite.share_kind,
                    amount_minor=invite.share_amount_minor,
                    percent_bp=invite.share_percent_bp,
                )
            await self._goals.add_member(goal.id, user_id, share, session=session)
            await self._accounts.add_owner(goal.account_id, user_id, session=session)

        status = GoalInviteStatus.ACCEPTED if command.accept else GoalInviteStatus.DECLINED
        responded_at = self._clock.now()
        await self._invites.set_status(invite.id, status, responded_at, session=session)

        after = invite.public_view() | {"status": status.value}
        events = [
            DomainEvent(
                name="goals.invite_responded",
                aggregate_type="goalInvite",
                aggregate_id=invite.id,
                payload={"userId": invite.invitee_id, "inviteId": invite.id, "status": status.value},
            ),
            DomainEvent(
                name="goals.invite_accepted" if command.accept else "goals.invite_declined",
                aggregate_type="goalInvite",
                aggregate_id=invite.id,
                payload={
                    "userId": invite.inviter_id,
                    "goalId": invite.goal_id,
                    "goalName": invite.goal_name,
                    "inviteeUsername": invite.invitee_username,
                },
            ),
        ]
        return CommandResult(
            data=after,
            audit=AuditRecord(
                action="goals.invite_responded",
                entity_type="goalInvite",
                entity_id=invite.id,
                before=invite.public_view(),
                after=after,
            ),
            events=events,
        )

    async def run_due_standing_orders(self) -> int:
        now = self._clock.now()
        due = await self._standing_orders.list_due(now)
        executed = 0
        for order in due:
            actor = Actor(kind="system", id="standing-orders-job", on_behalf_of=order.user_id)
            idempotency_key = f"{order.id}:{order.next_run_at.date().isoformat()}"
            try:
                await bus.execute(
                    RunStandingOrder(standing_order_id=order.id), actor, idempotency_key
                )
                executed += 1
            except Exception:
                logger.exception(
                    "standing_order_run_failed",
                    extra={"context": {"standingOrderId": order.id}},
                )
        return executed


@lru_cache(maxsize=1)
def get_goals_service() -> GoalsService:
    service = GoalsService(
        goals=MongoGoalRepository(),
        standing_orders=MongoStandingOrderRepository(),
        invites=MongoGoalInviteRepository(),
        accounts=get_accounts_service(),
        ledger=get_ledger_service(),
        users=MongoAuthUserRepository(),
        clock=SystemClock(),
    )
    service.register(bus)
    return service
