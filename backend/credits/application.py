from datetime import datetime, timezone
from typing import Any, Literal

from backend.helpers.context import new_id
from backend.helpers.errors import IllegalTransitionError
from pydantic import BaseModel, Field


class CreditApplication(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str
    product_id: str
    kind: str
    amount_minor: int
    term_months: int | None
    rate_bps: int
    purpose: str
    payout_account_id: str
    currency: str
    status: Literal["review", "withdrawn", "approved", "rejected"] = "review"
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    decision_reason: str | None = None
    decided_at: datetime | None = None
    decided_by: str | None = None

    def guard_decidable(self) -> None:
        if self.status != "review":
            raise IllegalTransitionError(
                "That application has already been decided.",
                details={"field": "applicationId", "status": self.status},
            )

    def public_view(self) -> dict[str, Any]:
        return {
            "applicationId": self.id,
            "productId": self.product_id,
            "kind": self.kind,
            "amount": {"minorUnits": self.amount_minor, "currency": self.currency},
            "termMonths": self.term_months,
            "rateBps": self.rate_bps,
            "purpose": self.purpose,
            "payoutAccountId": self.payout_account_id,
            "status": self.status,
            "submittedAt": self.submitted_at.isoformat(),
            "decisionReason": self.decision_reason,
            "decidedAt": self.decided_at.isoformat() if self.decided_at else None,
        }
