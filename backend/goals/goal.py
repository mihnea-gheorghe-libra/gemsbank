from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.helpers.context import new_id


class ContributionShare(BaseModel):
    user_id: str
    kind: Literal["fixed", "percent"]
    amount_minor: int | None = None
    percent_bp: int | None = None

    def public_view(self) -> dict[str, Any]:
        return {
            "userId": self.user_id,
            "kind": self.kind,
            "amountMinorUnits": self.amount_minor,
            "percentBp": self.percent_bp,
        }


class Goal(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str
    account_id: str
    parent_account_id: str
    name: str
    target_minor: int
    currency: str
    target_date: date
    status: Literal["active", "closed"] = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: datetime | None = None
    achieved_at: datetime | None = None
    streak_weeks: int = 0
    streak_last_week: str | None = None
    streak_computed_at: datetime | None = None
    member_ids: list[str] = Field(default_factory=list)
    contribution_plan: list[ContributionShare] = Field(default_factory=list)
    contributions_minor: dict[str, int] = Field(default_factory=dict)

    def uses_shared_parent_account(self) -> bool:
        return self.account_id == self.parent_account_id

    def is_owned_by(self, user_id: str) -> bool:
        return user_id == self.user_id or user_id in self.member_ids

    def is_shared(self) -> bool:
        return bool(self.member_ids) or bool(self.contribution_plan)

    def public_view(self) -> dict[str, Any]:
        return {
            "goalId": self.id,
            "accountId": self.account_id,
            "parentAccountId": self.parent_account_id,
            "name": self.name,
            "target": {"minorUnits": self.target_minor, "currency": self.currency},
            "targetDate": self.target_date.isoformat(),
            "status": self.status,
            "createdAt": self.created_at.isoformat(),
            "achievedAt": self.achieved_at.isoformat() if self.achieved_at else None,
            "streakWeeks": self.streak_weeks,
            "streakLastWeek": self.streak_last_week,
            "isShared": self.is_shared(),
        }
