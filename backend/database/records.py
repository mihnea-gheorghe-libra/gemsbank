from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClientSession
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from backend.database.mongo import (
    audit_log_collection,
    idempotency_collection,
    outbox_collection,
)
from backend.helpers.context import Actor, new_id
from backend.helpers.errors import ConflictError


class AuditRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    action: str
    entity_type: str
    entity_id: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


class DomainEvent(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    aggregate_type: str
    aggregate_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


async def write_audit(
    record: AuditRecord,
    actor: Actor,
    correlation_id: str,
    session: AsyncIOMotorClientSession | None = None,
) -> None:
    document = {
        "_id": record.id,
        "ts": datetime.now(timezone.utc),
        "actorKind": actor.kind,
        "actorId": actor.id,
        "onBehalfOf": actor.on_behalf_of,
        "mandateId": actor.mandate_id,
        "action": record.action,
        "entityType": record.entity_type,
        "entityId": record.entity_id,
        "before": record.before,
        "after": record.after,
        "correlationId": correlation_id,
    }
    await audit_log_collection().insert_one(document, session=session)


async def write_events(
    events: list[DomainEvent],
    correlation_id: str,
    session: AsyncIOMotorClientSession | None = None,
) -> None:
    if not events:
        return
    documents = [
        {
            "_id": event.id,
            "name": event.name,
            "aggregateType": event.aggregate_type,
            "aggregateId": event.aggregate_id,
            "payload": event.payload,
            "correlationId": correlation_id,
            "occurredAt": datetime.now(timezone.utc),
            "dispatchedAt": None,
        }
        for event in events
    ]
    await outbox_collection().insert_many(documents, session=session)


async def find_stored_response(scope: str, key: str) -> dict[str, Any] | None:
    document = await idempotency_collection().find_one({"scope": scope, "key": key})
    if document is None:
        return None
    return document.get("response")


async def store_response(
    scope: str,
    key: str,
    response: dict[str, Any],
    session: AsyncIOMotorClientSession | None = None,
) -> None:
    try:
        await idempotency_collection().insert_one(
            {
                "scope": scope,
                "key": key,
                "response": response,
                "createdAt": datetime.now(timezone.utc),
            },
            session=session,
        )
    except DuplicateKeyError as exc:
        raise ConflictError(
            "This idempotency key was already used for a different request.",
            details={"scope": scope},
        ) from exc
