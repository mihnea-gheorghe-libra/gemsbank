from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.helpers.context import new_id
from backend.helpers.errors import IllegalTransitionError


class GoalInviteStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"


class GoalInvite(BaseModel):
    id: str = Field(default_factory=new_id)
    goal_id: str
    goal_name: str
    currency: str
    inviter_id: str
    inviter_name: str
    invitee_id: str
    invitee_username: str
    share_kind: Literal["fixed", "percent"]
    share_amount_minor: int | None = None
    share_percent_bp: int | None = None
    status: GoalInviteStatus = GoalInviteStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    responded_at: datetime | None = None

    def guard_pending(self) -> None:
        if self.status is not GoalInviteStatus.PENDING:
            raise IllegalTransitionError(
                "This invitation was already answered.",
                details={"field": "inviteId", "status": self.status.value},
            )

    def public_view(self) -> dict[str, Any]:
        return {
            "inviteId": self.id,
            "goalId": self.goal_id,
            "goalName": self.goal_name,
            "currency": self.currency,
            "inviterId": self.inviter_id,
            "inviterName": self.inviter_name,
            "inviteeId": self.invitee_id,
            "inviteeUsername": self.invitee_username,
            "shareKind": self.share_kind,
            "shareAmountMinorUnits": self.share_amount_minor,
            "sharePercentBp": self.share_percent_bp,
            "status": self.status.value,
            "createdAt": self.created_at.isoformat(),
            "respondedAt": self.responded_at.isoformat() if self.responded_at else None,
        }
