from datetime import date, datetime, timezone
from typing import Any, Literal

from backend.helpers.context import new_id
from pydantic import BaseModel, Field


class TermDeposit(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str
    account_id: str
    parent_account_id: str
    name: str
    rate_bps: int
    term_months: int
    currency: str
    matures_at: date
    status: Literal["active", "closed"] = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: datetime | None = None

    def public_view(self) -> dict[str, Any]:
        return {
            "depositId": self.id,
            "accountId": self.account_id,
            "parentAccountId": self.parent_account_id,
            "name": self.name,
            "rateBps": self.rate_bps,
            "termMonths": self.term_months,
            "currency": self.currency,
            "maturesAt": self.matures_at.isoformat(),
            "status": self.status,
            "createdAt": self.created_at.isoformat(),
        }
