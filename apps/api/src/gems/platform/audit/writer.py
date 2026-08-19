from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClientSession
from pydantic import BaseModel, Field

from gems.platform.actors import Actor
from gems.platform.db.collections import audit_log_collection
from gems.platform.ids import new_id


class AuditRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    action: str
    entity_type: str
    entity_id: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


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
