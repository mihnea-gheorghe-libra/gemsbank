from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from backend.helpers.context import new_id
from backend.helpers.errors import IllegalTransitionError, ValidationError


class AccountKind(StrEnum):
    CURRENT = "current"
    SAVINGS = "savings"
    INVEST = "invest"


class AccountStatus(StrEnum):
    ACTIVE = "active"
    FROZEN = "frozen"
    CLOSED = "closed"


class Account(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str
    iban: str
    holder_name: str
    currency: str
    kind: AccountKind
    label: str
    status: AccountStatus = AccountStatus.ACTIVE
    opened_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def guard_can_send(self) -> None:
        if self.status is not AccountStatus.ACTIVE:
            raise IllegalTransitionError(
                f"This account is {self.status.value} and cannot send money.",
                details={"field": "sourceAccountId", "status": self.status.value},
            )

    def guard_can_receive(self) -> None:
        if self.status is AccountStatus.CLOSED:
            raise IllegalTransitionError(
                "That account is closed and cannot receive money.",
                details={"field": "iban", "status": self.status.value},
            )

    def guard_same_currency(self, other: "Account") -> None:
        if self.currency != other.currency:
            raise ValidationError(
                "GEMS does not convert currencies yet. Both accounts must hold the same one.",
                details={"field": "iban", "from": self.currency, "to": other.currency},
            )

    def guard_not_self(self, other: "Account") -> None:
        if self.id == other.id:
            raise ValidationError(
                "An account cannot pay itself.", details={"field": "iban"}
            )

    def guard_sufficient(self, balance_minor: int, amount_minor: int) -> None:
        if balance_minor < amount_minor:
            raise ValidationError(
                "That is more than this account holds.",
                details={
                    "field": "amount",
                    "availableMinorUnits": balance_minor,
                    "requestedMinorUnits": amount_minor,
                },
            )

    def masked_iban(self) -> str:
        return f"•• {self.iban[-4:]}"

    def public_view(self, balance_minor: int) -> dict[str, Any]:
        return {
            "accountId": self.id,
            "iban": self.iban,
            "ibanMasked": self.masked_iban(),
            "holderName": self.holder_name,
            "currency": self.currency,
            "kind": self.kind.value,
            "label": self.label,
            "status": self.status.value,
            "balance": {"minorUnits": balance_minor, "currency": self.currency},
        }
