import logging
import secrets
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, ClassVar, Protocol

from motor.motor_asyncio import AsyncIOMotorClientSession

from backend.auth import validation
from backend.auth.adapters import ResendResetCodeSender, SystemClock
from backend.auth.credentials import (
    GENERIC_PASSWORD_REJECTION,
    GENERIC_REJECTION,
    AuthUser,
    RecoveryCase,
    ResetChallenge,
    Session,
)
from backend.command_bus import Command, CommandBus, CommandResult, bus
from backend.config import Settings, settings
from backend.database.records import AuditRecord, DomainEvent
from backend.database.repositories import (
    MongoAuthUserRepository,
    MongoRecoveryCaseRepository,
    MongoSessionRepository,
)
from backend.helpers.context import Actor, ActorContext, log_event
from backend.helpers.crypto import (
    AesGcmPinCipher,
    Argon2idHasher,
    hash_token,
    new_opaque_token,
)
from backend.helpers.errors import AuthenticationError, DomainError, NotFoundError

logger = logging.getLogger(__name__)


class SignIn(Command):
    command_name: ClassVar[str] = "auth.sign_in"

    username: str
    pin: str


class RevealPin(Command):
    command_name: ClassVar[str] = "auth.reveal_pin"

    username: str
    password: str


class RequestPasswordReset(Command):
    command_name: ClassVar[str] = "auth.password_reset.request"

    username: str


class VerifyResetCode(Command):
    command_name: ClassVar[str] = "auth.password_reset.verify"

    recovery_case_id: str
    code: str


class ResetPassword(Command):
    command_name: ClassVar[str] = "auth.password_reset.complete"

    recovery_case_id: str
    password: str
    password_confirmation: str


class SignOut(Command):
    command_name: ClassVar[str] = "auth.sign_out"

    session_token: str


class SessionRepository(Protocol):
    async def add(
        self, record: Session, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def get_by_token_hash(self, token_hash: str) -> Session | None: ...

    async def revoke(
        self, record: Session, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...


class AuthUserRepository(Protocol):
    async def get_by_username(self, username: str) -> AuthUser | None: ...

    async def get(self, user_id: str) -> AuthUser | None: ...

    async def save(
        self, user: AuthUser, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...


class RecoveryCaseRepository(Protocol):
    async def add(
        self, case: RecoveryCase, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def get(self, case_id: str) -> RecoveryCase | None: ...

    async def save(
        self, case: RecoveryCase, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...


class PasswordHasher(Protocol):
    def hash(self, secret: str) -> str: ...

    def verify(self, secret: str, hashed: str) -> bool: ...


class PinCipher(Protocol):
    def decrypt(self, ciphertext: str, associated_data: str) -> str: ...


class ResetCodeSender(Protocol):
    async def send(self, email: str, code: str, expires_at: datetime) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class AuthService:
    def __init__(
        self,
        users: AuthUserRepository,
        cases: RecoveryCaseRepository,
        sessions: SessionRepository,
        hasher: PasswordHasher,
        cipher: PinCipher,
        code_sender: ResetCodeSender,
        clock: Clock,
        config: Settings,
    ) -> None:
        self._users = users
        self._cases = cases
        self._sessions = sessions
        self._hasher = hasher
        self._cipher = cipher
        self._codes = code_sender
        self._clock = clock
        self._config = config

    def register(self, command_bus: CommandBus) -> None:
        command_bus.register(SignIn, self._handle_sign_in)
        command_bus.register(RevealPin, self._handle_reveal_pin)
        command_bus.register(RequestPasswordReset, self._handle_reset_request)
        command_bus.register(VerifyResetCode, self._handle_reset_verify)
        command_bus.register(ResetPassword, self._handle_reset_complete)
        command_bus.register(SignOut, self._handle_sign_out)

    async def _issue_session(
        self, user: AuthUser, session: AsyncIOMotorClientSession
    ) -> dict[str, Any]:
        token = new_opaque_token()
        now = self._clock.now()
        record = Session(
            user_id=user.id,
            token_hash=hash_token(token),
            issued_at=now,
            expires_at=now + timedelta(seconds=self._config.session_ttl_seconds),
        )
        await self._sessions.add(record, session=session)
        return {"sessionToken": token} | record.public_view()

    async def resolve_actor(self, token: str) -> Actor:
        record = await self._sessions.get_by_token_hash(hash_token(token))
        if record is None:
            raise AuthenticationError("Sign in to continue.")
        record.guard_live(self._clock.now())
        user = await self._users.get(record.user_id)
        if user is None:
            raise AuthenticationError("Sign in to continue.")
        user.guard_usable(self._clock.now())
        return Actor.user(user.id)

    async def _handle_sign_out(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, SignOut)
        record = await self._sessions.get_by_token_hash(hash_token(command.session_token))
        if record is None:
            raise NotFoundError("That session is already gone.")
        record.revoke(self._clock.now())
        await self._sessions.revoke(record, session=session)

        return CommandResult(
            data={"signedOut": True},
            audit=AuditRecord(
                action="auth.signed_out",
                entity_type="session",
                entity_id=record.id,
                after={"userId": record.user_id},
            ),
            events=[
                DomainEvent(
                    name="auth.signed_out",
                    aggregate_type="session",
                    aggregate_id=record.id,
                )
            ],
        )

    async def _load_user(self, username: str, rejection: str) -> AuthUser:
        user = await self._users.get_by_username(username)
        if user is None:
            raise AuthenticationError(rejection)
        return user

    async def _load_case(self, case_id: str) -> RecoveryCase:
        case = await self._cases.get(case_id)
        if case is None:
            raise NotFoundError("Reset request not found. Start again.")
        return case

    def _reveal_payload(self, user: AuthUser) -> dict[str, Any]:
        return {"pin": self._cipher.decrypt(user.require_recoverable_pin(), user.id)}

    def _optional_reveal_payload(self, user: AuthUser) -> dict[str, Any]:
        if not user.pin_encrypted:
            log_event(logger, "pin.not_recoverable", userId=user.id)
            return {"pin": None}
        return self._reveal_payload(user)

    async def _handle_sign_in(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, SignIn)
        username = validation.normalise_username(command.username)
        pin = validation.validate_pin_shape(command.pin)
        user = await self._load_user(username, GENERIC_REJECTION)

        matches = self._hasher.verify(pin, user.pin_hash)
        try:
            user.sign_in(
                matches,
                self._config.sign_in_max_failures,
                self._config.sign_in_lockout_seconds,
                self._clock.now(),
            )
        except DomainError:
            await self._users.save(user)
            raise
        await self._users.save(user, session=session)
        granted = await self._issue_session(user, session)

        return CommandResult(
            data=user.public_view(),
            sensitive=granted,
            audit=AuditRecord(
                action="auth.signed_in",
                entity_type="user",
                entity_id=user.id,
                after={"username": user.username},
            ),
            events=[
                DomainEvent(
                    name="auth.signed_in",
                    aggregate_type="user",
                    aggregate_id=user.id,
                )
            ],
        )

    async def _handle_reveal_pin(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, RevealPin)
        username = validation.normalise_username(command.username)
        user = await self._load_user(username, GENERIC_PASSWORD_REJECTION)

        matches = self._hasher.verify(command.password, user.password_hash)
        try:
            user.authorise_reveal(
                matches,
                self._config.reveal_max_failures,
                self._config.sign_in_lockout_seconds,
                self._clock.now(),
            )
        except DomainError:
            await self._users.save(user)
            raise
        revealed = self._reveal_payload(user)
        await self._users.save(user, session=session)
        granted = await self._issue_session(user, session)

        return CommandResult(
            data=user.public_view(),
            sensitive=revealed | granted,
            audit=AuditRecord(
                action="auth.pin_revealed",
                entity_type="user",
                entity_id=user.id,
                after={"username": user.username, "via": "password"},
            ),
            events=[
                DomainEvent(
                    name="auth.pin_revealed",
                    aggregate_type="user",
                    aggregate_id=user.id,
                )
            ],
        )

    async def _handle_reset_request(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, RequestPasswordReset)
        username = validation.normalise_username(command.username)
        user = await self._users.get_by_username(username)
        if user is None:
            raise NotFoundError(
                "No account uses that username.", details={"field": "username"}
            )
        user.guard_usable(self._clock.now())

        code = f"{secrets.randbelow(1_000_000):06d}"
        now = self._clock.now()
        case = RecoveryCase(
            user_id=user.id,
            otp=ResetChallenge(
                code_hash=self._hasher.hash(code),
                expires_at=now + timedelta(seconds=self._config.reset_code_ttl_seconds),
                sent_at=now,
            ),
        )
        await self._cases.add(case, session=session)
        assert case.otp is not None
        await self._codes.send(user.email, code, case.otp.expires_at)

        delivery: dict[str, Any] = {
            "sentTo": validation.mask_email(user.email),
            "expiresAt": case.otp.expires_at.isoformat(),
        }
        if not self._config.resend_api_key:
            delivery["devCode"] = code
            log_event(logger, "reset_code.dev_mode", recoveryCaseId=case.id, code=code)

        return CommandResult(
            data=case.public_view() | {"delivery": delivery},
            audit=AuditRecord(
                action="auth.password_reset_requested",
                entity_type="user",
                entity_id=user.id,
                after={"recoveryCaseId": case.id, "email": validation.mask_email(user.email)},
            ),
            events=[
                DomainEvent(
                    name="auth.password_reset_requested",
                    aggregate_type="user",
                    aggregate_id=user.id,
                    payload={"recoveryCaseId": case.id},
                )
            ],
        )

    async def _handle_reset_verify(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, VerifyResetCode)
        case = await self._load_case(command.recovery_case_id)
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
                action="auth.password_reset_code_verified",
                entity_type="recoveryCase",
                entity_id=case.id,
                before={"status": before},
                after={"status": case.status.value},
            ),
            events=[
                DomainEvent(
                    name="auth.password_reset_code_verified",
                    aggregate_type="recoveryCase",
                    aggregate_id=case.id,
                )
            ],
        )

    async def _handle_reset_complete(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, ResetPassword)
        case = await self._load_case(command.recovery_case_id)
        before = case.status.value

        password = validation.validate_new_password(
            command.password, command.password_confirmation
        )
        user = await self._users.get(case.user_id)
        if user is None:
            raise NotFoundError("The account for this reset request no longer exists.")

        case.complete()
        user.change_password(self._hasher.hash(password))
        revealed = self._optional_reveal_payload(user)

        await self._users.save(user, session=session)
        await self._cases.save(case, session=session)
        granted = await self._issue_session(user, session)

        return CommandResult(
            data=case.public_view() | user.public_view(),
            sensitive=revealed | granted,
            audit=AuditRecord(
                action="auth.password_changed",
                entity_type="user",
                entity_id=user.id,
                before={"status": before},
                after={"status": case.status.value, "recoveryCaseId": case.id},
            ),
            events=[
                DomainEvent(
                    name="auth.password_changed",
                    aggregate_type="user",
                    aggregate_id=user.id,
                    payload={"recoveryCaseId": case.id},
                )
            ],
        )


@lru_cache(maxsize=1)
def get_auth_service() -> AuthService:
    service = AuthService(
        users=MongoAuthUserRepository(),
        cases=MongoRecoveryCaseRepository(),
        sessions=MongoSessionRepository(),
        hasher=Argon2idHasher(),
        cipher=AesGcmPinCipher(settings.pin_encryption_key),
        code_sender=ResendResetCodeSender(settings),
        clock=SystemClock(),
        config=settings,
    )
    service.register(bus)
    return service
