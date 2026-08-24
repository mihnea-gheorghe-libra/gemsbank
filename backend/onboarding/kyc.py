from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from backend.helpers.context import new_id
from backend.helpers.errors import (
    EligibilityError,
    IllegalTransitionError,
    RateLimitedError,
    ValidationError,
)


class OnboardingStatus(StrEnum):
    STARTED = "started"
    DOCUMENT_SUBMITTED = "document_submitted"
    CONTACT_PROVIDED = "contact_provided"
    CODE_VERIFIED = "code_verified"
    COMPLETED = "completed"


STEP_OF_STATUS: dict[OnboardingStatus, int] = {
    OnboardingStatus.STARTED: 1,
    OnboardingStatus.DOCUMENT_SUBMITTED: 2,
    OnboardingStatus.CONTACT_PROVIDED: 3,
    OnboardingStatus.CODE_VERIFIED: 4,
    OnboardingStatus.COMPLETED: 4,
}

TOTAL_STEPS = 4


def age_in_years(birth: date, today: date) -> int:
    years = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        years -= 1
    return years


class ExtractedIdentity(BaseModel):
    full_name: str
    birth_date: date
    cnp_masked: str
    document_number_masked: str
    expires_on: date
    cnp_raw: str | None = None


class SubmittedDocument(BaseModel):
    doc_ref: str
    doc_type: str
    extracted: ExtractedIdentity
    submitted_at: datetime


class Contact(BaseModel):
    email: str
    phone: str


class OtpChallenge(BaseModel):
    code_hash: str
    expires_at: datetime
    sent_at: datetime
    attempts: int = 0
    resends: int = 0


class KycCase(BaseModel):
    id: str = Field(default_factory=new_id)
    status: OnboardingStatus = OnboardingStatus.STARTED
    document: SubmittedDocument | None = None
    contact: Contact | None = None
    otp: OtpChallenge | None = None
    user_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def current_step(self) -> int:
        return STEP_OF_STATUS[self.status]

    def _touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def _require(self, *allowed: OnboardingStatus) -> None:
        if self.status not in allowed:
            raise IllegalTransitionError(
                f"Onboarding is at step '{self.status}' and cannot accept this action.",
                details={"status": self.status.value, "expected": [s.value for s in allowed]},
            )

    def submit_document(self, document: SubmittedDocument, now: datetime, minimum_age: int) -> None:
        self._require(OnboardingStatus.STARTED, OnboardingStatus.DOCUMENT_SUBMITTED)
        age = age_in_years(document.extracted.birth_date, now.date())
        if age < minimum_age:
            raise EligibilityError(
                f"You must be at least {minimum_age} to open a GEMS account.",
                details={
                    "field": "birthDate",
                    "minimumAge": minimum_age,
                    "ageYears": age,
                    "birthDate": document.extracted.birth_date.isoformat(),
                },
            )
        self.document = document
        self.status = OnboardingStatus.DOCUMENT_SUBMITTED
        self._touch()

    def set_contact(self, contact: Contact, challenge: OtpChallenge) -> None:
        self._require(
            OnboardingStatus.DOCUMENT_SUBMITTED,
            OnboardingStatus.CONTACT_PROVIDED,
        )
        self.contact = contact
        self.otp = challenge
        self.status = OnboardingStatus.CONTACT_PROVIDED
        self._touch()

    def resend_code(
        self,
        challenge: OtpChallenge,
        cooldown_seconds: int,
        max_resends: int,
        now: datetime,
    ) -> None:
        self._require(OnboardingStatus.CONTACT_PROVIDED)
        if self.otp is None:
            raise IllegalTransitionError("There is no code to resend yet.")
        if self.otp.resends >= max_resends:
            raise RateLimitedError(
                "You reached the maximum number of resends. Start again or contact support.",
                details={"maxResends": max_resends},
            )
        elapsed = (now - self.otp.sent_at).total_seconds()
        if elapsed < cooldown_seconds:
            raise RateLimitedError(
                "Please wait before requesting another code.",
                details={"retryAfterSeconds": int(cooldown_seconds - elapsed)},
            )
        challenge.resends = self.otp.resends + 1
        self.otp = challenge
        self._touch()

    def verify_code(self, matches: bool, max_attempts: int, now: datetime) -> None:
        self._require(OnboardingStatus.CONTACT_PROVIDED)
        if self.otp is None:
            raise IllegalTransitionError("No code has been sent for this case.")
        if self.otp.attempts >= max_attempts:
            raise RateLimitedError("Too many failed attempts. Request a new code.")
        if now > self.otp.expires_at:
            raise ValidationError("The code expired. Request a new one.")
        if not matches:
            self.otp.attempts += 1
            self._touch()
            raise ValidationError(
                "Incorrect code.",
                details={"attemptsLeft": max(max_attempts - self.otp.attempts, 0)},
            )
        self.otp = None
        self.status = OnboardingStatus.CODE_VERIFIED
        self._touch()

    def complete(self, user_id: str) -> None:
        self._require(OnboardingStatus.CODE_VERIFIED)
        if self.document is None or self.contact is None:
            raise IllegalTransitionError("Onboarding is missing document or contact data.")
        self.user_id = user_id
        self.status = OnboardingStatus.COMPLETED
        self._touch()

    def _extracted_view(self) -> dict[str, Any]:
        assert self.document is not None
        extracted = self.document.extracted
        return {
            "fullName": extracted.full_name,
            "birthDate": extracted.birth_date.isoformat(),
            "ageYears": age_in_years(extracted.birth_date, datetime.now(timezone.utc).date()),
            "cnp": extracted.cnp_raw or extracted.cnp_masked,
            "cnpMasked": extracted.cnp_masked,
            "documentNumberMasked": extracted.document_number_masked,
            "expiresOn": extracted.expires_on.isoformat(),
        }


    def public_view(self) -> dict[str, Any]:
        return {
            "kycCaseId": self.id,
            "status": self.status.value,
            "step": self.current_step,
            "totalSteps": TOTAL_STEPS,
            "extracted": self._extracted_view() if self.document else None,
            "contact": {"email": self.contact.email, "phone": self.contact.phone}
            if self.contact
            else None,
        }
