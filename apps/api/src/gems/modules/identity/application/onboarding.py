import logging
import secrets
from datetime import datetime, timedelta

from motor.motor_asyncio import AsyncIOMotorClientSession

from gems.config import Settings
from gems.modules.identity.application.commands import (
    CompleteOnboarding,
    ResendCode,
    SetContact,
    StartOnboarding,
    SubmitIdentityDocument,
    VerifyCode,
)
from gems.modules.identity.application.ports import (
    Clock,
    DocumentExtractor,
    KycCaseRepository,
    OtpSender,
    PasswordHasher,
    UserRepository,
)
from gems.modules.identity.domain import credentials
from gems.modules.identity.domain.kyc import (
    Contact,
    KycCase,
    OtpChallenge,
    SubmittedDocument,
)
from gems.platform.actors import ActorContext
from gems.platform.audit.writer import AuditRecord
from gems.platform.commandbus.bus import Command, CommandBus, CommandResult
from gems.platform.errors import ConflictError, DomainError, NotFoundError
from gems.platform.ids import new_id
from gems.platform.observability.correlation import log_event
from gems.platform.outbox.writer import DomainEvent

logger = logging.getLogger(__name__)

ALLOWED_DOC_TYPES = {"ci_front", "passport"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class OnboardingService:
    def __init__(
        self,
        cases: KycCaseRepository,
        users: UserRepository,
        hasher: PasswordHasher,
        otp_sender: OtpSender,
        extractor: DocumentExtractor,
        clock: Clock,
        config: Settings,
    ) -> None:
        self._cases = cases
        self._users = users
        self._hasher = hasher
        self._otp = otp_sender
        self._extractor = extractor
        self._clock = clock
        self._config = config

    def register(self, bus: CommandBus) -> None:
        bus.register(StartOnboarding, self._handle_start)
        bus.register(SubmitIdentityDocument, self._handle_document)
        bus.register(SetContact, self._handle_contact)
        bus.register(ResendCode, self._handle_resend)
        bus.register(VerifyCode, self._handle_verify)
        bus.register(CompleteOnboarding, self._handle_complete)

    async def get_case(self, case_id: str) -> dict:
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

    async def _deliver_code(self, case: KycCase, code: str) -> dict:
        assert case.contact is not None
        assert case.otp is not None
        await self._otp.send(case.contact.email, code, case.otp.expires_at)
        payload = {
            "sentTo": credentials.mask_email(case.contact.email),
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

        email = credentials.normalise_email(command.email)
        phone = credentials.normalise_phone(command.phone)
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
                after={"status": case.status.value, "email": credentials.mask_email(email)},
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

        username = credentials.normalise_username(command.username)
        password = credentials.validate_password(command.password)
        pin = credentials.validate_pin(command.pin, command.pin_confirmation)

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
            kyc_case_id=case.id,
            session=session,
        )
        await self._cases.save(case, session=session)

        return CommandResult(
            data={"userId": user_id, "username": username} | case.public_view(),
            audit=AuditRecord(
                action="identity.user_registered",
                entity_type="user",
                entity_id=user_id,
                before={"status": before},
                after={"username": username, "kycCaseId": case.id},
            ),
            events=[
                DomainEvent(
                    name="identity.user_registered",
                    aggregate_type="user",
                    aggregate_id=user_id,
                    payload={"kycCaseId": case.id},
                )
            ],
        )
