from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import lru_cache
from typing import ClassVar, Protocol

from motor.motor_asyncio import AsyncIOMotorClientSession

from backend.accounts.service import AccountsService, get_accounts_service
from backend.command_bus import Command, CommandBus, CommandResult, bus
from backend.database.records import AuditRecord, DomainEvent
from backend.database.repositories import MongoGoalRepository
from backend.goals import validation
from backend.goals.goal import Goal
from backend.helpers.context import ActorContext
from backend.helpers.errors import ConflictError
from backend.ledger.service import LedgerService, get_ledger_service

__all__ = ["Goal", "GoalProgress", "GoalsService", "get_goals_service"]


class GoalRepository(Protocol):
    async def add(
        self, goal: Goal, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def get(self, goal_id: str) -> Goal | None: ...

    async def get_for_user(self, user_id: str) -> Goal | None: ...


class Clock(Protocol):
    def today(self) -> date: ...


class SystemClock:
    def today(self) -> date:
        return datetime.now(timezone.utc).date()


@dataclass(slots=True, frozen=True)
class GoalProgress:
    goal: Goal
    progress_minor: int


class CreateGoal(Command):
    command_name: ClassVar[str] = "goals.create"

    account_id: str
    name: str
    target_minor: int
    target_date: date


class GoalsService:
    def __init__(
        self, goals: GoalRepository, accounts: AccountsService, ledger: LedgerService, clock: Clock
    ) -> None:
        self._goals = goals
        self._accounts = accounts
        self._ledger = ledger
        self._clock = clock

    def register(self, command_bus: CommandBus) -> None:
        command_bus.register(CreateGoal, self._handle_create)

    async def get_for_user(self, user_id: str) -> Goal | None:
        return await self._goals.get_for_user(user_id)

    async def get_progress_for_user(self, user_id: str) -> GoalProgress | None:
        goal = await self._goals.get_for_user(user_id)
        if goal is None:
            return None
        account = await self._accounts.get_owned(goal.account_id, user_id)
        balances = await self._ledger.balances_of([account.id])
        return GoalProgress(goal=goal, progress_minor=balances.get(account.id, 0))

    async def _handle_create(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, CreateGoal)
        user_id = context.actor.subject_id()

        existing = await self._goals.get_for_user(user_id)
        if existing is not None:
            raise ConflictError(
                "You already have a goal. GEMS supports one active goal per user for now.",
                details={"field": "goalId", "existingGoalId": existing.id},
            )

        account = await self._accounts.get_owned(command.account_id, user_id)
        today = self._clock.today()
        goal = Goal(
            user_id=user_id,
            account_id=account.id,
            name=validation.normalise_name(command.name),
            target_minor=validation.normalise_target_minor(command.target_minor),
            currency=account.currency,
            target_date=validation.normalise_target_date(command.target_date, today),
        )
        await self._goals.add(goal, session=session)

        return CommandResult(
            data=goal.public_view(),
            audit=AuditRecord(
                action="goals.created",
                entity_type="goal",
                entity_id=goal.id,
                after=goal.public_view(),
            ),
            events=[
                DomainEvent(name="goals.created", aggregate_type="goal", aggregate_id=goal.id)
            ],
        )


@lru_cache(maxsize=1)
def get_goals_service() -> GoalsService:
    service = GoalsService(
        goals=MongoGoalRepository(),
        accounts=get_accounts_service(),
        ledger=get_ledger_service(),
        clock=SystemClock(),
    )
    service.register(bus)
    return service
