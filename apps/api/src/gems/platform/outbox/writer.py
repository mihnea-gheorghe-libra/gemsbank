from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClientSession
from pydantic import BaseModel, Field

from gems.platform.db.collections import outbox_collection
from gems.platform.ids import new_id


class DomainEvent(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    aggregate_type: str
    aggregate_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


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
