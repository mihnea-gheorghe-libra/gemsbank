from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, ClassVar

from motor.motor_asyncio import AsyncIOMotorClientSession
from pydantic import BaseModel

from backend.database.mongo import get_client
from backend.database.records import (
    AuditRecord,
    DomainEvent,
    find_stored_response,
    store_response,
    write_audit,
    write_events,
)
from backend.helpers.context import Actor, ActorContext, get_correlation_id
from backend.helpers.errors import ValidationError


class Command(BaseModel):
    command_name: ClassVar[str]


@dataclass(slots=True)
class CommandResult:
    data: dict[str, Any]
    audit: AuditRecord
    events: list[DomainEvent] = field(default_factory=list)
    sensitive: dict[str, Any] = field(default_factory=dict)


Handler = Callable[[Command, ActorContext, AsyncIOMotorClientSession], Awaitable[CommandResult]]


class CommandBus:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, command_type: type[Command], handler: Handler) -> None:
        name = command_type.command_name
        if name in self._handlers:
            raise ValueError(f"Command '{name}' already has a handler.")
        self._handlers[name] = handler

    def registered_commands(self) -> list[str]:
        return sorted(self._handlers)

    async def execute(
        self,
        command: Command,
        actor: Actor,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        name = type(command).command_name
        handler = self._handlers.get(name)
        if handler is None:
            raise ValidationError(f"No handler registered for command '{name}'.")

        if idempotency_key:
            replayed = await find_stored_response(name, idempotency_key)
            if replayed is not None:
                return replayed

        context = ActorContext(actor=actor, correlation_id=get_correlation_id())

        async with await get_client().start_session() as session:
            async with session.start_transaction():
                result = await handler(command, context, session)
                await write_audit(result.audit, actor, context.correlation_id, session=session)
                await write_events(result.events, context.correlation_id, session=session)
                if idempotency_key:
                    await store_response(name, idempotency_key, result.data, session=session)

        return result.data | result.sensitive


bus = CommandBus()
