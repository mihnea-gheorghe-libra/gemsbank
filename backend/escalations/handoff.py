from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from backend.helpers.context import new_id


class HandoffStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class Handoff(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str
    question: str
    reason: str | None = None
    transcript: list[dict[str, str]] = Field(default_factory=list)
    status: HandoffStatus = HandoffStatus.OPEN
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def public_view(self) -> dict[str, Any]:
        return {
            "handoffId": self.id,
            "status": self.status.value,
            "createdAt": self.created_at.isoformat(),
        }
