from datetime import date, datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from backend.helpers.context import new_id


class Goal(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str
    account_id: str
    name: str
    target_minor: int
    currency: str
    target_date: date
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def public_view(self) -> dict[str, Any]:
        return {
            "goalId": self.id,
            "accountId": self.account_id,
            "name": self.name,
            "target": {"minorUnits": self.target_minor, "currency": self.currency},
            "targetDate": self.target_date.isoformat(),
            "createdAt": self.created_at.isoformat(),
        }
