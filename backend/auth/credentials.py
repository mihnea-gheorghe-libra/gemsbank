from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from backend.helpers.context import new_id
from backend.helpers.errors import (
    AuthenticationError,
    IllegalTransitionError,
    RateLimitedError,
    ValidationError,
)

GENERIC_REJECTION = "That username and PIN do not match an account."
GENERIC_PASSWORD_REJECTION = "That username and password do not match an account."


class RecoveryStatus(StrEnum):
    CODE_SENT = "code_sent"
    CODE_VERIFIED = "code_verified"
    COMPLETED = "completed"


class ResetChallenge(BaseModel):
    code_hash: str
    expires_at: datetime
    sent_at: datetime
    attempts: int = 0


class AuthUser(BaseModel):
    id: str
    username: str
    email: str
    password_hash: str
    pin_hash: str
    pin_encrypted: str | None = None
    status: str = "active"
    failures: int = 0
    locked_until: datetime | None = None

    def _touch_lock(self, max_failures: int, lockout_seconds: int, now: datetime) -> None:
        self.failures += 1
        if self.failures >= max_failures:
            self.locked_until = now + timedelta(seconds=lockout_seconds)

    def guard_usable(self, now: datetime) -> None:
        if self.status != "active":
            raise AuthenticationError("This account is not active. Contact support.")
        if self.locked_until is not None and now < self.locked_until:
            raise RateLimitedError(
                "Too many failed attempts. Try again later.",
                details={"retryAfterSeconds": int((self.locked_until - now).total_seconds())},
            )

    def _accept(self) -> None:
        self.failures = 0
        self.locked_until = None

    def sign_in(
        self, pin_matches: bool, max_failures: int, lockout_seconds: int, now: datetime
    ) -> None:
        self.guard_usable(now)
        if not pin_matches:
            self._touch_lock(max_failures, lockout_seconds, now)
            raise AuthenticationError(
                GENERIC_REJECTION,
                details={"attemptsLeft": max(max_failures - self.failures, 0)},
            )
        self._accept()

    def authorise_reveal(
        self, password_matches: bool, max_failures: int, lockout_seconds: int, now: datetime
    ) -> None:
        self.guard_usable(now)
        if not password_matches:
            self._touch_lock(max_failures, lockout_seconds, now)
            raise AuthenticationError(
                GENERIC_PASSWORD_REJECTION,
                details={"field": "password", "attemptsLeft": max(max_failures - self.failures, 0)},
            )
        self._accept()

    def require_recoverable_pin(self) -> str:
        if not self.pin_encrypted:
            raise IllegalTransitionError(
                "Your username and password are correct, but this account was created before "
                "PIN recovery existed, so there is no stored PIN to show.",
                details={"field": "pin"},
            )
        return self.pin_encrypted

    def change_password(self, password_hash: str) -> None:
        self.password_hash = password_hash
        self._accept()

    def public_view(self) -> dict[str, Any]:
        return {"userId": self.id, "username": self.username}


class Session(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str
    token_hash: str
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    def guard_live(self, now: datetime) -> None:
        if self.revoked_at is not None:
            raise AuthenticationError("You are signed out. Sign in again.")
        if now >= self.expires_at:
            raise AuthenticationError("Your session expired. Sign in again.")

    def revoke(self, now: datetime) -> None:
        if self.revoked_at is None:
            self.revoked_at = now

    def public_view(self) -> dict[str, Any]:
        return {"sessionId": self.id, "expiresAt": self.expires_at.isoformat()}


class RecoveryCase(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str
    status: RecoveryStatus = RecoveryStatus.CODE_SENT
    otp: ResetChallenge | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def _touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def _require(self, *allowed: RecoveryStatus) -> None:
        if self.status not in allowed:
            raise IllegalTransitionError(
                f"This reset request is at step '{self.status}' and cannot accept this action.",
                details={"status": self.status.value, "expected": [s.value for s in allowed]},
            )

    def verify_code(self, matches: bool, max_attempts: int, now: datetime) -> None:
        self._require(RecoveryStatus.CODE_SENT)
        if self.otp is None:
            raise IllegalTransitionError("No code has been sent for this request.")
        if self.otp.attempts >= max_attempts:
            raise RateLimitedError("Too many failed attempts. Start the reset again.")
        if now > self.otp.expires_at:
            raise ValidationError("The code expired. Start the reset again.")
        if not matches:
            self.otp.attempts += 1
            self._touch()
            raise ValidationError(
                "Incorrect code.",
                details={"attemptsLeft": max(max_attempts - self.otp.attempts, 0)},
            )
        self.otp = None
        self.status = RecoveryStatus.CODE_VERIFIED
        self._touch()

    def complete(self) -> None:
        self._require(RecoveryStatus.CODE_VERIFIED)
        self.status = RecoveryStatus.COMPLETED
        self._touch()

    def public_view(self) -> dict[str, Any]:
        return {"recoveryCaseId": self.id, "status": self.status.value}
