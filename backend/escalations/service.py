from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, ClassVar, Protocol

from motor.motor_asyncio import AsyncIOMotorClientSession

from backend.agents.transcript import sanitise_history
from backend.command_bus import Command, CommandBus, CommandResult, bus
from backend.database.records import AuditRecord, DomainEvent
from backend.database.repositories import MongoHandoffRepository
from backend.escalations import validation
from backend.escalations.handoff import Handoff
from backend.helpers.context import ActorContext

__all__ = ["EscalationsService", "Handoff", "RequestHandoff", "get_escalations_service"]


class HandoffRepository(Protocol):
    async def add(
        self, handoff: Handoff, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def list_for_user(self, user_id: str) -> list[Handoff]: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class RequestHandoff(Command):
    command_name: ClassVar[str] = "support.handoff.request"

    question: str
    reason: str | None = None
    transcript: list[dict[str, str]] | None = None


class EscalationsService:
    def __init__(self, handoffs: HandoffRepository, clock: Clock) -> None:
        self._handoffs = handoffs
        self._clock = clock

    def register(self, command_bus: CommandBus) -> None:
        command_bus.register(RequestHandoff, self._handle_request)

    async def list_for_user(self, user_id: str) -> dict[str, Any]:
        found = await self._handoffs.list_for_user(user_id)
        return {"handoffs": [item.public_view() for item in found]}

    async def _handle_request(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, RequestHandoff)
        user_id = context.actor.subject_id()

        handoff = Handoff(
            user_id=user_id,
            question=validation.normalise_question(command.question),
            reason=validation.normalise_reason(command.reason),
            transcript=sanitise_history(command.transcript),
            created_at=self._clock.now(),
        )
        await self._handoffs.add(handoff, session=session)

        return CommandResult(
            data=handoff.public_view(),
            audit=AuditRecord(
                action="support.handoff_requested",
                entity_type="handoff",
                entity_id=handoff.id,
                after={"userId": user_id, "reason": handoff.reason},
            ),
            events=[
                DomainEvent(
                    name="support.handoff_requested",
                    aggregate_type="handoff",
                    aggregate_id=handoff.id,
                    payload={"userId": user_id, "status": handoff.status.value},
                )
            ],
        )


@lru_cache(maxsize=1)
def get_escalations_service() -> EscalationsService:
    service = EscalationsService(handoffs=MongoHandoffRepository(), clock=SystemClock())
    service.register(bus)
    return service
