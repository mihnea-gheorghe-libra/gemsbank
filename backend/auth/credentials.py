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


class RecoveryKind(StrEnum):
    PASSWORD_RESET = "password_reset"
    EMAIL_CHANGE = "email_change"
    PHONE_CHANGE = "phone_change"
    PIN_CHANGE = "pin_change"


class ResetChallenge(BaseModel):
    code_hash: str
    expires_at: datetime
    sent_at: datetime
    attempts: int = 0


class AuthUser(BaseModel):
    id: str
    username: str
    email: str
    phone: str
    full_name: str
    password_hash: str
    pin_hash: str
    pin_encrypted: str | None = None
    status: str = "active"
    pin_failures: int = 0
    pin_locked: bool = False
    password_failures: int = 0
    password_lockout_stage: int = 0
    password_locked_until: datetime | None = None
    prefs: dict[str, Any] = Field(default_factory=dict)

    def guard_usable(self, now: datetime) -> None:
        if self.status != "active":
            raise AuthenticationError("This account is not active. Contact support.")

    def _guard_password_not_locked(self, now: datetime) -> None:
        if self.password_locked_until is not None and now < self.password_locked_until:
            raise RateLimitedError(
                "Too many failed attempts. Try again later.",
                details={
                    "field": "password",
                    "retryAfterSeconds": int((self.password_locked_until - now).total_seconds()),
                },
            )

    def _accept_pin(self) -> None:
        self.pin_failures = 0
        self.pin_locked = False

    def _accept_password(self) -> None:
        self.password_failures = 0
        self.password_lockout_stage = 0
        self.password_locked_until = None

    def sign_in(self, pin_matches: bool, max_failures: int, now: datetime) -> None:
        self.guard_usable(now)
        if self.pin_locked:
            raise AuthenticationError(
                "Too many incorrect PIN attempts. Sign in with your password instead.",
                details={"field": "pin", "pinLocked": True},
            )
        if not pin_matches:
            self.pin_failures += 1
            if self.pin_failures >= max_failures:
                self.pin_locked = True
            raise AuthenticationError(
                GENERIC_REJECTION,
                details={
                    "attemptsLeft": max(max_failures - self.pin_failures, 0),
                    "pinLocked": self.pin_locked,
                },
            )
        self._accept_pin()

    def authorise_reveal(
        self,
        password_matches: bool,
        max_failures: int,
        lockout_seconds: int,
        extended_lockout_seconds: int,
        now: datetime,
    ) -> None:
        self.guard_usable(now)
        self._guard_password_not_locked(now)
        if not password_matches:
            self.password_failures += 1
            if self.password_failures >= max_failures:
                if self.password_lockout_stage == 0:
                    self.password_lockout_stage = 1
                    self.password_locked_until = now + timedelta(seconds=lockout_seconds)
                elif self.password_lockout_stage == 1:
                    self.password_lockout_stage = 2
                    self.password_locked_until = now + timedelta(seconds=extended_lockout_seconds)
                else:
                    self.password_lockout_stage = 3
                    self.password_locked_until = None
                    self.status = "locked"
            if self.password_lockout_stage == 3:
                raise AuthenticationError(
                    "Too many failed attempts. This account has been locked. Contact support.",
                    details={"field": "password", "permanentlyLocked": True},
                )
            details: dict[str, Any] = {
                "field": "password",
                "attemptsLeft": max(max_failures - self.password_failures, 0),
            }
            if self.password_locked_until is not None:
                details["retryAfterSeconds"] = int(
                    (self.password_locked_until - now).total_seconds()
                )
            raise AuthenticationError(GENERIC_PASSWORD_REJECTION, details=details)
        self._accept_password()
        self._accept_pin()

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
        self._accept_password()
        self._accept_pin()

    def change_email(self, new_email: str) -> None:
        self.email = new_email

    def change_phone(self, new_phone: str) -> None:
        self.phone = new_phone

    def change_pin(self, pin_hash: str, pin_encrypted: str) -> None:
        self.pin_hash = pin_hash
        self.pin_encrypted = pin_encrypted
        self._accept_pin()

    def verify_pin_for_reauth(self, matches: bool) -> None:
        self.guard_usable(datetime.now(timezone.utc))
        if not matches:
            raise AuthenticationError(GENERIC_REJECTION, details={"field": "pin"})

    def public_view(self) -> dict[str, Any]:
        return {"userId": self.id, "username": self.username, "prefs": self.prefs}

    def me_view(self) -> dict[str, Any]:
        return {
            "userId": self.id,
            "username": self.username,
            "email": self.email,
            "phone": self.phone,
            "fullName": self.full_name,
        }


class Session(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str
    token_hash: str
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    user_agent: str | None = None
    ip_address: str | None = None

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
    kind: RecoveryKind = RecoveryKind.PASSWORD_RESET
    status: RecoveryStatus = RecoveryStatus.CODE_SENT
    otp: ResetChallenge | None = None
    payload: dict[str, str] = Field(default_factory=dict)
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
