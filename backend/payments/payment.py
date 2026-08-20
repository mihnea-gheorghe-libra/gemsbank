from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from backend.helpers.context import new_id
from backend.helpers.errors import (
    IllegalTransitionError,
    RateLimitedError,
    ValidationError,
)


class PaymentStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_SIGNATURE = "awaiting_signature"
    PENDING = "pending"
    POSTED = "posted"
    REJECTED = "rejected"


class PaymentRail(StrEnum):
    INTERNAL = "internal"
    SEPA = "sepa"


class PayeeVerification(StrEnum):
    MATCH = "match"
    CLOSE_MATCH = "close_match"
    NO_MATCH = "no_match"
    NOT_CHECKED = "not_checked"


class SignatureChallenge(BaseModel):
    code_hash: str
    expires_at: datetime
    issued_at: datetime
    attempts: int = 0


class Beneficiary(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str
    name: str
    iban: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def public_view(self) -> dict[str, Any]:
        return {
            "beneficiaryId": self.id,
            "name": self.name,
            "iban": self.iban,
            "createdAt": self.created_at.isoformat(),
        }


class Payment(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str
    rail: PaymentRail = PaymentRail.INTERNAL
    status: PaymentStatus = PaymentStatus.DRAFT
    source_account_id: str
    target_account_id: str | None = None
    target_iban: str
    counterparty: str
    amount_minor: int
    currency: str
    reference: str
    category: str
    payee_check: PayeeVerification = PayeeVerification.NOT_CHECKED
    signature: SignatureChallenge | None = None
    journal_transaction_id: str | None = None
    rejected_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def _touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def _require(self, *allowed: PaymentStatus) -> None:
        if self.status not in allowed:
            raise IllegalTransitionError(
                f"This payment is '{self.status}' and cannot accept this action.",
                details={"status": self.status.value, "expected": [s.value for s in allowed]},
            )

    def require_signature(self, challenge: SignatureChallenge) -> None:
        self._require(PaymentStatus.DRAFT)
        self.signature = challenge
        self.status = PaymentStatus.AWAITING_SIGNATURE
        self._touch()

    def sign(self, matches: bool, max_attempts: int, now: datetime) -> None:
        self._require(PaymentStatus.AWAITING_SIGNATURE)
        if self.signature is None:
            raise IllegalTransitionError("No signature was requested for this payment.")
        if self.signature.attempts >= max_attempts:
            raise RateLimitedError(
                "Too many failed signatures. Start the payment again.",
                details={"paymentId": self.id},
            )
        if now > self.signature.expires_at:
            raise ValidationError(
                "The signature code expired. Start the payment again.",
                details={"field": "code"},
            )
        if not matches:
            self.signature.attempts += 1
            self._touch()
            raise ValidationError(
                "Incorrect signature code.",
                details={
                    "field": "code",
                    "attemptsLeft": max(max_attempts - self.signature.attempts, 0),
                },
            )
        self.signature = None
        self.status = PaymentStatus.DRAFT
        self._touch()

    def mark_posted(self, journal_transaction_id: str) -> None:
        self._require(PaymentStatus.DRAFT)
        self.journal_transaction_id = journal_transaction_id
        self.status = PaymentStatus.POSTED
        self._touch()

    def reject(self, reason: str) -> None:
        self._require(PaymentStatus.DRAFT, PaymentStatus.AWAITING_SIGNATURE)
        self.rejected_reason = reason
        self.signature = None
        self.status = PaymentStatus.REJECTED
        self._touch()

    def public_view(self) -> dict[str, Any]:
        return {
            "paymentId": self.id,
            "status": self.status.value,
            "rail": self.rail.value,
            "sourceAccountId": self.source_account_id,
            "counterparty": self.counterparty,
            "iban": self.target_iban,
            "reference": self.reference,
            "category": self.category,
            "payeeCheck": self.payee_check.value,
            "amount": {"minorUnits": self.amount_minor, "currency": self.currency},
            "createdAt": self.created_at.isoformat(),
            "signatureExpiresAt": self.signature.expires_at.isoformat()
            if self.signature
            else None,
        }

    def receipt_view(self) -> dict[str, Any]:
        return self.public_view() | {
            "journalTransactionId": self.journal_transaction_id,
            "postedAt": self.updated_at.isoformat(),
        }

    def movement_view(self) -> dict[str, Any]:
        return {
            "transactionId": self.journal_transaction_id or self.id,
            "paymentId": self.id,
            "accountId": self.source_account_id,
            "postedAt": self.created_at.isoformat(),
            "kind": "internal_transfer",
            "counterparty": self.counterparty,
            "reference": self.reference,
            "category": self.category,
            "status": self.status.value,
            "direction": "debit",
            "amount": {"minorUnits": -self.amount_minor, "currency": self.currency},
        }
