import logging
import secrets
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, ClassVar, Protocol

from motor.motor_asyncio import AsyncIOMotorClientSession

from backend.command_bus import Command, CommandBus, CommandResult, bus
from backend.config import Settings, settings
from backend.database.records import AuditRecord, DomainEvent
from backend.database.repositories import MongoKycCaseRepository, MongoUserRepository
from backend.helpers.context import ActorContext, log_event, new_id
from backend.helpers.crypto import AesGcmPinCipher, Argon2idHasher
from backend.helpers.errors import ConflictError, DomainError, NotFoundError
from backend.onboarding import validation
from backend.onboarding.adapters import (
    AzureDocIntelDocumentExtractor,
    ResendOtpSender,
    SystemClock,
)
from backend.onboarding.kyc import (
    Contact,
    ExtractedIdentity,
    KycCase,
    OtpChallenge,
    SubmittedDocument,
)
from backend.payments.service import get_payments_service

logger = logging.getLogger(__name__)


class StartOnboarding(Command):
    command_name: ClassVar[str] = "identity.onboarding.start"


class SubmitIdentityDocument(Command):
    command_name: ClassVar[str] = "identity.onboarding.submit_document"

    kyc_case_id: str
    doc_type: str
    filename: str
    content: bytes


class SetContact(Command):
    command_name: ClassVar[str] = "identity.onboarding.set_contact"

    kyc_case_id: str
    email: str
    phone: str


class ResendCode(Command):
    command_name: ClassVar[str] = "identity.onboarding.resend_code"

    kyc_case_id: str


class VerifyCode(Command):
    command_name: ClassVar[str] = "identity.onboarding.verify_code"

    kyc_case_id: str
    code: str


class CompleteOnboarding(Command):
    command_name: ClassVar[str] = "identity.onboarding.complete"

    kyc_case_id: str
    username: str
    password: str
    password_confirmation: str
    pin: str
    pin_confirmation: str
    prefs: dict[str, Any] | None = None


class KycCaseRepository(Protocol):
    async def add(
        self, case: KycCase, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def get(self, case_id: str) -> KycCase | None: ...

    async def save(
        self, case: KycCase, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...


class UserRepository(Protocol):
    async def create(
        self,
        user_id: str,
        username: str,
        email: str,
        phone: str,
        password_hash: str,
        pin_hash: str,
        pin_encrypted: str,
        kyc_case_id: str,
        prefs: dict[str, Any] | None = None,
        session: AsyncIOMotorClientSession | None = None,
    ) -> None: ...

    async def exists_username(self, username: str) -> bool: ...

    async def exists_email(self, email: str) -> bool: ...


class PasswordHasher(Protocol):
    def hash(self, secret: str) -> str: ...

    def verify(self, secret: str, hashed: str) -> bool: ...


class PinCipher(Protocol):
    def encrypt(self, plaintext: str, associated_data: str) -> str: ...


class OtpSender(Protocol):
    async def send(self, email: str, code: str, expires_at: datetime) -> None: ...


class DocumentExtractor(Protocol):
    async def extract(self, doc_type: str, content: bytes, filename: str) -> ExtractedIdentity: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class AccountProvisioning(Protocol):
    async def provision_starter_accounts(
        self,
        user_id: str,
        holder_name: str,
        correlation_id: str,
        actor: str,
        session: AsyncIOMotorClientSession | None = None,
    ) -> list[str]: ...


class OnboardingService:
    def __init__(
        self,
        cases: KycCaseRepository,
        users: UserRepository,
        provisioning: AccountProvisioning,
        hasher: PasswordHasher,
        cipher: PinCipher,
        otp_sender: OtpSender,
        extractor: DocumentExtractor,
        clock: Clock,
        config: Settings,
    ) -> None:
        self._cases = cases
        self._users = users
        self._provisioning = provisioning
        self._hasher = hasher
        self._cipher = cipher
        self._otp = otp_sender
        self._extractor = extractor
        self._clock = clock
        self._config = config

    def register(self, command_bus: CommandBus) -> None:
        command_bus.register(StartOnboarding, self._handle_start)
        command_bus.register(SubmitIdentityDocument, self._handle_document)
        command_bus.register(SetContact, self._handle_contact)
        command_bus.register(ResendCode, self._handle_resend)
        command_bus.register(VerifyCode, self._handle_verify)
        command_bus.register(CompleteOnboarding, self._handle_complete)

    async def get_case(self, case_id: str) -> dict[str, Any]:
        case = await self._load(case_id)
        return case.public_view()

    async def _load(self, case_id: str) -> KycCase:
        case = await self._cases.get(case_id)
        if case is None:
            raise NotFoundError("Onboarding session not found. Start again.")
        return case

    def _new_challenge(self, code: str, now: datetime) -> OtpChallenge:
        return OtpChallenge(
            code_hash=self._hasher.hash(code),
            expires_at=now + timedelta(seconds=self._config.otp_ttl_seconds),
            sent_at=now,
        )

    async def _deliver_code(self, case: KycCase, code: str) -> dict[str, Any]:
        assert case.contact is not None
        assert case.otp is not None
        await self._otp.send(case.contact.email, code, case.otp.expires_at)
        payload: dict[str, Any] = {
            "sentTo": validation.mask_email(case.contact.email),
            "expiresAt": case.otp.expires_at.isoformat(),
            "resendAvailableInSeconds": self._config.otp_resend_cooldown_seconds,
            "resendsLeft": self._config.otp_max_resends - case.otp.resends,
        }
        if not self._config.resend_api_key:
            payload["devCode"] = code
            log_event(logger, "otp.dev_mode", kycCaseId=case.id, code=code)
        return payload

    async def _handle_start(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, StartOnboarding)
        case = KycCase()
        await self._cases.add(case, session=session)
        return CommandResult(
            data=case.public_view(),
            audit=AuditRecord(
                action="onboarding.started",
                entity_type="kycCase",
                entity_id=case.id,
                after={"status": case.status.value},
            ),
            events=[
                DomainEvent(
                    name="identity.onboarding.started",
                    aggregate_type="kycCase",
                    aggregate_id=case.id,
                )
            ],
        )

    async def _handle_document(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, SubmitIdentityDocument)
        case = await self._load(command.kyc_case_id)
        before = case.status.value

        extracted = await self._extractor.extract(
            command.doc_type, command.content, command.filename
        )
        document = SubmittedDocument(
            doc_ref=f"demo:{command.doc_type}:{new_id()}",
            doc_type=command.doc_type,
            extracted=extracted,
            submitted_at=self._clock.now(),
        )
        case.submit_document(document, self._clock.now(), self._config.minimum_age_years)
        await self._cases.save(case, session=session)

        return CommandResult(
            data=case.public_view(),
            audit=AuditRecord(
                action="onboarding.document_submitted",
                entity_type="kycCase",
                entity_id=case.id,
                before={"status": before},
                after={"status": case.status.value, "docRef": document.doc_ref},
            ),
            events=[
                DomainEvent(
                    name="identity.onboarding.document_submitted",
                    aggregate_type="kycCase",
                    aggregate_id=case.id,
                    payload={"docType": document.doc_type},
                )
            ],
        )

    async def _handle_contact(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, SetContact)
        case = await self._load(command.kyc_case_id)
        before = case.status.value

        email = validation.normalise_email(command.email)
        phone = validation.normalise_phone(command.phone)
        if await self._users.exists_email(email):
            raise ConflictError(
                "An account already uses this email address.", details={"field": "email"}
            )

        code = f"{secrets.randbelow(1_000_000):06d}"
        now = self._clock.now()
        case.set_contact(Contact(email=email, phone=phone), self._new_challenge(code, now))
        await self._cases.save(case, session=session)
        delivery = await self._deliver_code(case, code)

        return CommandResult(
            data=case.public_view() | {"delivery": delivery},
            audit=AuditRecord(
                action="onboarding.contact_provided",
                entity_type="kycCase",
                entity_id=case.id,
                before={"status": before},
                after={"status": case.status.value, "email": validation.mask_email(email)},
            ),
            events=[
                DomainEvent(
                    name="identity.onboarding.code_sent",
                    aggregate_type="kycCase",
                    aggregate_id=case.id,
                )
            ],
        )

    async def _handle_resend(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, ResendCode)
        case = await self._load(command.kyc_case_id)

        code = f"{secrets.randbelow(1_000_000):06d}"
        now = self._clock.now()
        case.resend_code(
            self._new_challenge(code, now),
            self._config.otp_resend_cooldown_seconds,
            self._config.otp_max_resends,
            now,
        )
        await self._cases.save(case, session=session)
        delivery = await self._deliver_code(case, code)

        return CommandResult(
            data=case.public_view() | {"delivery": delivery},
            audit=AuditRecord(
                action="onboarding.code_resent",
                entity_type="kycCase",
                entity_id=case.id,
                after={"resends": case.otp.resends if case.otp else 0},
            ),
            events=[
                DomainEvent(
                    name="identity.onboarding.code_sent",
                    aggregate_type="kycCase",
                    aggregate_id=case.id,
                    payload={"resend": True},
                )
            ],
        )

    async def _handle_verify(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, VerifyCode)
        case = await self._load(command.kyc_case_id)
        before = case.status.value

        challenge = case.otp
        matches = challenge is not None and self._hasher.verify(command.code, challenge.code_hash)
        try:
            case.verify_code(matches, self._config.otp_max_attempts, self._clock.now())
        except DomainError:
            await self._cases.save(case)
            raise
        await self._cases.save(case, session=session)

        return CommandResult(
            data=case.public_view(),
            audit=AuditRecord(
                action="onboarding.code_verified",
                entity_type="kycCase",
                entity_id=case.id,
                before={"status": before},
                after={"status": case.status.value},
            ),
            events=[
                DomainEvent(
                    name="identity.onboarding.code_verified",
                    aggregate_type="kycCase",
                    aggregate_id=case.id,
                )
            ],
        )

    async def _handle_complete(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, CompleteOnboarding)
        case = await self._load(command.kyc_case_id)
        before = case.status.value

        username = validation.normalise_username(command.username)
        password = validation.validate_password(command.password, command.password_confirmation)
        pin = validation.validate_pin(command.pin, command.pin_confirmation)

        if await self._users.exists_username(username):
            raise ConflictError("That username is taken.", details={"field": "username"})

        assert case.contact is not None
        user_id = new_id()
        case.complete(user_id)

        await self._users.create(
            user_id=user_id,
            username=username,
            email=case.contact.email,
            phone=case.contact.phone,
            password_hash=self._hasher.hash(password),
            pin_hash=self._hasher.hash(pin),
            pin_encrypted=self._cipher.encrypt(pin, user_id),
            kyc_case_id=case.id,
            prefs=command.prefs,
            session=session,
        )
        await self._cases.save(case, session=session)

        assert case.document is not None
        account_ids = await self._provisioning.provision_starter_accounts(
            user_id=user_id,
            holder_name=case.document.extracted.full_name,
            correlation_id=context.correlation_id,
            actor=context.actor.label(),
            session=session,
        )

        return CommandResult(
            data={"userId": user_id, "username": username, "accountsOpened": len(account_ids)}
            | case.public_view(),
            audit=AuditRecord(
                action="identity.user_registered",
                entity_type="user",
                entity_id=user_id,
                before={"status": before},
                after={
                    "username": username,
                    "kycCaseId": case.id,
                    "accountIds": account_ids,
                },
            ),
            events=[
                DomainEvent(
                    name="identity.user_registered",
                    aggregate_type="user",
                    aggregate_id=user_id,
                    payload={"kycCaseId": case.id, "accountIds": account_ids},
                )
            ],
        )


@lru_cache(maxsize=1)
def get_onboarding_service() -> OnboardingService:
    service = OnboardingService(
        cases=MongoKycCaseRepository(),
        users=MongoUserRepository(),
        provisioning=get_payments_service(),
        hasher=Argon2idHasher(),
        cipher=AesGcmPinCipher(settings.pin_encryption_key),
        otp_sender=ResendOtpSender(settings),
        extractor=AzureDocIntelDocumentExtractor(
            endpoint=settings.azure_docintel_endpoint,
            key=settings.azure_docintel_key,
            min_confidence=settings.ocr_min_confidence
        ),

        clock=SystemClock(),
        config=settings,
    )
    service.register(bus)
    return service
