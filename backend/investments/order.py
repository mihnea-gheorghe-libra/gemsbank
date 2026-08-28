from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from backend.helpers.context import new_id


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class InvestmentOrder(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str
    account_id: str
    instrument_id: str
    side: OrderSide
    quantity_micro: int
    unit_price_minor: int
    amount_minor: int
    currency: str
    journal_transaction_id: str
    executed_at: datetime

    def public_view(self) -> dict[str, Any]:
        return {
            "orderId": self.id,
            "accountId": self.account_id,
            "instrumentId": self.instrument_id,
            "side": self.side.value,
            "quantityMicro": self.quantity_micro,
            "unitPriceMinor": self.unit_price_minor,
            "amountMinor": self.amount_minor,
            "currency": self.currency,
            "executedAt": self.executed_at.isoformat(),
        }
