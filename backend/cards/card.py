from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from backend.helpers.context import new_id
from backend.helpers.errors import IllegalTransitionError


class CardKind(StrEnum):
    PHYSICAL_DEBIT = "physical_debit"
    VIRTUAL_MASTERCARD = "virtual_mastercard"
    VIRTUAL_SINGLE_USE = "virtual_single_use"
    PHYSICAL_METAL = "physical_metal"


class CardState(StrEnum):
    ACTIVE = "active"
    FROZEN = "frozen"
    BLOCKED = "blocked"


class Card(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str
    kind: CardKind
    last4: str
    owner_name: str
    currency: str = "RON"
    expires_on: date
    state: CardState = CardState.ACTIVE
    pin_encrypted: str
    cvv_encrypted: str | None = None
    atm_limit_minor: int
    online_limit_minor: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def _touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def _guard_not_blocked(self) -> None:
        if self.state == CardState.BLOCKED:
            raise IllegalTransitionError(
                "This card is permanently blocked and cannot be changed.",
                details={"state": self.state.value},
            )

    def freeze(self) -> None:
        self._guard_not_blocked()
        if self.state == CardState.FROZEN:
            raise IllegalTransitionError("This card is already frozen.")
        self.state = CardState.FROZEN
        self._touch()

    def unfreeze(self) -> None:
        self._guard_not_blocked()
        if self.state != CardState.FROZEN:
            raise IllegalTransitionError("This card is not frozen.")
        self.state = CardState.ACTIVE
        self._touch()

    def block_permanently(self) -> None:
        if self.state == CardState.BLOCKED:
            raise IllegalTransitionError("This card is already blocked.")
        self.state = CardState.BLOCKED
        self._touch()

    def set_atm_limit(self, minor: int) -> None:
        self._guard_not_blocked()
        self.atm_limit_minor = minor
        self._touch()

    def set_online_limit(self, minor: int) -> None:
        self._guard_not_blocked()
        self.online_limit_minor = minor
        self._touch()

    def require_revealable(self) -> None:
        self._guard_not_blocked()

    def require_cvv_revealable(self) -> str:
        self._guard_not_blocked()
        if not self.cvv_encrypted:
            raise IllegalTransitionError(
                "This card was issued before CVV reveal existed, so there is no CVV to show."
            )
        return self.cvv_encrypted

    def masked_number(self) -> str:
        return f"•••• •••• •••• {self.last4}"

    def public_view(self) -> dict[str, Any]:
        return {
            "cardId": self.id,
            "kind": self.kind.value,
            "numberMasked": self.masked_number(),
            "owner": self.owner_name,
            "currency": self.currency,
            "expiresOn": self.expires_on.isoformat(),
            "state": self.state.value,
            "atmLimitMinor": self.atm_limit_minor,
            "onlineLimitMinor": self.online_limit_minor,
        }
