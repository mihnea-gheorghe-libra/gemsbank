from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.helpers.context import new_id

Frequency = Literal["weekly", "monthly"]
StandingOrderStatus = Literal["active", "paused", "cancelled"]
CreatedVia = Literal["user", "agent-suggestion-confirmed"]


class StandingOrder(BaseModel):
    id: str = Field(default_factory=new_id)
    goal_id: str
    user_id: str
    source_account_id: str
    target_account_id: str
    amount_minor: int
    currency: str
    frequency: Frequency
    next_run_at: datetime
    status: StandingOrderStatus = "active"
    created_via: CreatedVia = "user"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_run_at: datetime | None = None
    last_failure_reason: str | None = None

    def public_view(self) -> dict[str, Any]:
        return {
            "standingOrderId": self.id,
            "goalId": self.goal_id,
            "amount": {"minorUnits": self.amount_minor, "currency": self.currency},
            "frequency": self.frequency,
            "nextRunAt": self.next_run_at.isoformat(),
            "status": self.status,
            "createdVia": self.created_via,
            "lastRunAt": self.last_run_at.isoformat() if self.last_run_at else None,
            "lastFailureReason": self.last_failure_reason,
        }
