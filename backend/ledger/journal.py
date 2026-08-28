from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from backend.helpers.context import new_id
from backend.helpers.errors import ValidationError

MINIMUM_ENTRIES = 2


class HouseAccount(StrEnum):
    SETTLEMENT = "house:settlement"
    FEE_REVENUE = "house:fee_revenue"
    SUSPENSE = "house:suspense"
    FX = "house:fx"


def house_account_id(account: HouseAccount, currency: str) -> str:
    return f"{account.value}:{currency}"


class TransactionKind(StrEnum):
    OPENING_DEPOSIT = "opening_deposit"
    INTERNAL_TRANSFER = "internal_transfer"
    FEE = "fee"
    REVERSAL = "reversal"
    FX_CONVERSION = "fx_conversion"
    DEMO_TOPUP = "demo_topup"
    INVESTMENT_BUY = "investment_buy"
    INVESTMENT_SELL = "investment_sell"


class EntrySide(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class JournalEntry(BaseModel):
    account_id: str
    amount: int

    @property
    def side(self) -> EntrySide:
        return EntrySide.CREDIT if self.amount > 0 else EntrySide.DEBIT


class JournalTransaction(BaseModel):
    id: str = Field(default_factory=new_id)
    currency: str
    kind: TransactionKind
    entries: list[JournalEntry]
    reference: str
    counterparty: str
    category: str
    posted_at: datetime
    correlation_id: str
    actor: str
    reverses: str | None = None

    @model_validator(mode="after")
    def _balanced(self) -> "JournalTransaction":
        if len(self.entries) < MINIMUM_ENTRIES:
            raise ValidationError(
                "A journal transaction needs at least two entries.",
                details={"entries": len(self.entries)},
            )
        if any(entry.amount == 0 for entry in self.entries):
            raise ValidationError("A journal entry cannot be for zero.")
        total = sum(entry.amount for entry in self.entries)
        if total != 0:
            raise ValidationError(
                "Journal entries must sum to zero per currency.",
                details={"currency": self.currency, "residual": total},
            )
        return self

    def entry_for(self, account_id: str) -> JournalEntry | None:
        for entry in self.entries:
            if entry.account_id == account_id:
                return entry
        return None

    def movement_view(self, account_id: str) -> dict[str, Any]:
        entry = self.entry_for(account_id)
        if entry is None:
            raise ValidationError(
                "That account has no entry in this transaction.",
                details={"accountId": account_id},
            )
        return {
            "transactionId": self.id,
            "accountId": account_id,
            "postedAt": self.posted_at.isoformat(),
            "kind": self.kind.value,
            "counterparty": self.counterparty,
            "reference": self.reference,
            "category": self.category,
            "status": "booked",
            "direction": entry.side.value,
            "amount": {"minorUnits": entry.amount, "currency": self.currency},
        }
