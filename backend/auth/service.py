import logging
import secrets
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, ClassVar, Protocol

from motor.motor_asyncio import AsyncIOMotorClientSession

from backend.auth import validation
from backend.auth.adapters import (
    ResendResetCodeSender,
    SystemClock,
    classify_location,
    describe_device,
)
from backend.auth.credentials import (
    GENERIC_PASSWORD_REJECTION,
    GENERIC_REJECTION,
    AuthUser,
    RecoveryCase,
    RecoveryKind,
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
from backend.helpers.errors import (
    AuthenticationError,
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)

logger = logging.getLogger(__name__)


class SignIn(Command):
    command_name: ClassVar[str] = "auth.sign_in"

    username: str
    pin: str


class VerifyPin(Command):
    command_name: ClassVar[str] = "auth.verify_pin"

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


class RequestUsernameChange(Command):
    command_name: ClassVar[str] = "auth.username_change.request"

    new_username: str


class RequestEmailChange(Command):
    command_name: ClassVar[str] = "auth.email_change.request"

    new_email: str


class RequestPhoneChange(Command):
    command_name: ClassVar[str] = "auth.phone_change.request"

    new_phone: str


class RequestPinChange(Command):
    command_name: ClassVar[str] = "auth.pin_change.request"

    new_pin: str
    new_pin_confirmation: str


class RequestPasswordChange(Command):
    command_name: ClassVar[str] = "auth.password_change.request"

    new_password: str
    new_password_confirmation: str


class VerifySecureChange(Command):
    command_name: ClassVar[str] = "auth.secure_change.verify"

    case_id: str
    code: str


class RequestAccountClosure(Command):
    command_name: ClassVar[str] = "auth.account_closure.request"

    pin: str


class RevokeSession(Command):
    command_name: ClassVar[str] = "auth.session.revoke"

    session_id: str
class UpdatePreferences(Command):
    command_name: ClassVar[str] = "auth.update_preferences"
    
    user_id: str
    prefs: dict[str, Any]


class SessionRepository(Protocol):
    async def add(
        self, record: Session, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def get(self, session_id: str) -> Session | None: ...

    async def get_by_token_hash(self, token_hash: str) -> Session | None: ...

    async def list_live_for_user(self, user_id: str, now: datetime) -> list[Session]: ...

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
    def encrypt(self, plaintext: str, associated_data: str) -> str: ...

    def decrypt(self, ciphertext: str, associated_data: str) -> str: ...


class ResetCodeSender(Protocol):
    async def send(
        self,
        email: str,
        code: str,
        expires_at: datetime,
        purpose: str = "resetarea parolei",
        subject: str = "Resetare parolă GEMS",
    ) -> None: ...


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
        command_bus.register(VerifyPin, self._handle_verify_pin)
        command_bus.register(RevealPin, self._handle_reveal_pin)
        command_bus.register(RequestPasswordReset, self._handle_reset_request)
        command_bus.register(VerifyResetCode, self._handle_reset_verify)
        command_bus.register(ResetPassword, self._handle_reset_complete)
        command_bus.register(SignOut, self._handle_sign_out)
        command_bus.register(RequestUsernameChange, self._handle_request_username_change)
        command_bus.register(RequestEmailChange, self._handle_request_email_change)
        command_bus.register(RequestPhoneChange, self._handle_request_phone_change)
        command_bus.register(RequestPinChange, self._handle_request_pin_change)
        command_bus.register(RequestPasswordChange, self._handle_request_password_change)
        command_bus.register(VerifySecureChange, self._handle_verify_secure_change)
        command_bus.register(RequestAccountClosure, self._handle_account_closure_request)
        command_bus.register(RevokeSession, self._handle_revoke_session)
        command_bus.register(UpdatePreferences, self._handle_update_preferences)

    async def _issue_session(
        self,
        user: AuthUser,
        session: AsyncIOMotorClientSession,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        token = new_opaque_token()
        now = self._clock.now()
        record = Session(
            user_id=user.id,
            token_hash=hash_token(token),
            issued_at=now,
            expires_at=now + timedelta(seconds=self._config.session_ttl_seconds),
            ip_address=ip_address,
            user_agent=user_agent,
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

    async def _handle_update_preferences(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, UpdatePreferences)
        if context.actor.id != command.user_id:
            raise AuthenticationError("Unauthorized")
        user = await self._users.get(command.user_id)
        if not user:
            raise NotFoundError("User not found")
        user.prefs.update(command.prefs)
        await self._users.save(user, session=session)
        
        return CommandResult(
            data={"prefs": user.prefs},
            audit=AuditRecord(
                action="auth.preferences_updated",
                entity_type="user",
                entity_id=user.id,
                after={"prefs": user.prefs},
            ),
        )

    async def _load_user(self, username: str, rejection: str) -> AuthUser:
        user = await self._users.get_by_username(username)
        if user is None:
            raise AuthenticationError("No account exists with that username.")
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
                self._config.pin_max_failures,
                self._clock.now(),
            )
        except DomainError:
            await self._users.save(user)
            raise
        await self._users.save(user, session=session)
        granted = await self._issue_session(
            user, session, ip_address=context.ip, user_agent=context.user_agent
        )

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

    async def verify_user_pin(self, user_id: str, pin: str) -> bool:
        user = await self._users.get(user_id)
        if user is None:
            return False
        return self._hasher.verify(pin, user.pin_hash)

    async def _handle_verify_pin(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, VerifyPin)
        username = validation.normalise_username(command.username)
        pin = validation.validate_pin_shape(command.pin)
        user = await self._load_user(username, GENERIC_REJECTION)
        user.guard_usable(self._clock.now())

        if not self._hasher.verify(pin, user.pin_hash):
            raise AuthenticationError(GENERIC_REJECTION)

        return CommandResult(
            data={"verified": True},
            audit=AuditRecord(
                action="auth.pin_verified",
                entity_type="user",
                entity_id=user.id,
                after={"username": user.username},
            ),
            events=[
                DomainEvent(
                    name="auth.pin_verified",
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
                self._config.password_max_failures,
                self._config.password_lockout_seconds,
                self._config.password_lockout_extended_seconds,
                self._clock.now(),
            )
        except DomainError:
            await self._users.save(user)
            raise
        revealed = self._reveal_payload(user)
        await self._users.save(user, session=session)
        granted = await self._issue_session(
            user, session, ip_address=context.ip, user_agent=context.user_agent
        )

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
        granted = await self._issue_session(
            user, session, ip_address=context.ip, user_agent=context.user_agent
        )

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

    async def _current_user(self, context: ActorContext) -> AuthUser:
        user = await self._users.get(context.actor.id)
        if user is None:
            raise AuthenticationError("Sign in to continue.")
        return user

    async def _start_secure_change(
        self,
        user: AuthUser,
        kind: RecoveryKind,
        payload: dict[str, str],
        purpose: str,
        subject: str,
        session: AsyncIOMotorClientSession,
    ) -> CommandResult:
        code = f"{secrets.randbelow(1_000_000):06d}"
        now = self._clock.now()
        case = RecoveryCase(
            user_id=user.id,
            kind=kind,
            otp=ResetChallenge(
                code_hash=self._hasher.hash(code),
                expires_at=now + timedelta(seconds=self._config.reset_code_ttl_seconds),
                sent_at=now,
            ),
            payload=payload,
        )
        await self._cases.add(case, session=session)
        assert case.otp is not None
        await self._codes.send(user.email, code, case.otp.expires_at, purpose=purpose, subject=subject)

        delivery: dict[str, Any] = {
            "sentTo": validation.mask_email(user.email),
            "expiresAt": case.otp.expires_at.isoformat(),
        }
        if not self._config.resend_api_key:
            delivery["devCode"] = code
            log_event(logger, "secure_change.dev_mode", recoveryCaseId=case.id, code=code, kind=kind.value)

        return CommandResult(
            data=case.public_view() | {"delivery": delivery},
            audit=AuditRecord(
                action=f"auth.{kind.value}_requested",
                entity_type="user",
                entity_id=user.id,
                after={"recoveryCaseId": case.id},
            ),
            events=[
                DomainEvent(
                    name=f"auth.{kind.value}_requested",
                    aggregate_type="user",
                    aggregate_id=user.id,
                    payload={"recoveryCaseId": case.id},
                )
            ],
        )

    async def _handle_request_username_change(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, RequestUsernameChange)
        user = await self._current_user(context)
        new_username = validation.normalise_username(command.new_username)
        if new_username == user.username:
            raise ValidationError(
                "That is already your username.", details={"field": "username"}
            )
        taken = await self._users.get_by_username(new_username)
        if taken is not None and taken.id != user.id:
            raise ConflictError("That username is taken.", details={"field": "username"})
        user.change_username(new_username)
        await self._users.save(user, session=session)
        return CommandResult(
            data=user.me_view(),
            audit=AuditRecord(action="auth.username_changed", entity_type="user", entity_id=user.id, after={"username": new_username}),
            events=[DomainEvent(name="auth.username_changed", aggregate_type="user", aggregate_id=user.id)]
        )

    async def _handle_request_email_change(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, RequestEmailChange)
        user = await self._current_user(context)
        new_email = validation.normalise_email(command.new_email)
        user.change_email(new_email)
        await self._users.save(user, session=session)
        return CommandResult(
            data=user.me_view(),
            audit=AuditRecord(action="auth.email_changed", entity_type="user", entity_id=user.id, after={"email": new_email}),
            events=[DomainEvent(name="auth.email_changed", aggregate_type="user", aggregate_id=user.id)]
        )

    async def _handle_request_phone_change(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, RequestPhoneChange)
        user = await self._current_user(context)
        new_phone = validation.normalise_phone(command.new_phone)
        user.change_phone(new_phone)
        await self._users.save(user, session=session)
        return CommandResult(
            data=user.me_view(),
            audit=AuditRecord(action="auth.phone_changed", entity_type="user", entity_id=user.id, after={"phone": new_phone}),
            events=[DomainEvent(name="auth.phone_changed", aggregate_type="user", aggregate_id=user.id)]
        )

    async def _handle_request_pin_change(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, RequestPinChange)
        user = await self._current_user(context)
        new_pin = validation.validate_new_pin(command.new_pin, command.new_pin_confirmation)
        return await self._start_secure_change(
            user,
            RecoveryKind.PIN_CHANGE,
            {"newPin": new_pin},
            purpose="schimbarea PIN-ului",
            subject="Confirmă schimbarea PIN-ului — GEMS",
            session=session,
        )

    async def _handle_request_password_change(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, RequestPasswordChange)
        user = await self._current_user(context)
        new_password = validation.validate_new_password(
            command.new_password, command.new_password_confirmation
        )
        return await self._start_secure_change(
            user,
            RecoveryKind.PASSWORD_CHANGE,
            {"newPassword": new_password},
            purpose="schimbarea parolei",
            subject="Confirmă schimbarea parolei — GEMS",
            session=session,
        )

    async def _handle_verify_secure_change(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, VerifySecureChange)
        case = await self._load_case(command.case_id)
        if case.user_id != context.actor.id:
            raise NotFoundError("Reset request not found. Start again.")
        before = case.status.value

        challenge = case.otp
        matches = challenge is not None and self._hasher.verify(command.code, challenge.code_hash)
        try:
            case.verify_code(matches, self._config.otp_max_attempts, self._clock.now())
        except DomainError:
            await self._cases.save(case)
            raise
        case.complete()

        user = await self._users.get(case.user_id)
        if user is None:
            raise NotFoundError("The account for this request no longer exists.")

        if case.kind == RecoveryKind.USERNAME_CHANGE:
            new_username = case.payload["newUsername"]
            taken = await self._users.get_by_username(new_username)
            if taken is not None and taken.id != user.id:
                raise ConflictError(
                    "That username is taken.", details={"field": "username"}
                )
            user.change_username(new_username)
        elif case.kind == RecoveryKind.EMAIL_CHANGE:
            user.change_email(case.payload["newEmail"])
        elif case.kind == RecoveryKind.PHONE_CHANGE:
            user.change_phone(case.payload["newPhone"])
        elif case.kind == RecoveryKind.PIN_CHANGE:
            new_pin = case.payload["newPin"]
            user.change_pin(self._hasher.hash(new_pin), self._cipher.encrypt(new_pin, user.id))
        elif case.kind == RecoveryKind.PASSWORD_CHANGE:
            user.change_password(self._hasher.hash(case.payload["newPassword"]))

        await self._users.save(user, session=session)
        await self._cases.save(case, session=session)

        return CommandResult(
            data=case.public_view() | user.me_view(),
            audit=AuditRecord(
                action=f"auth.{case.kind.value}_completed",
                entity_type="user",
                entity_id=user.id,
                before={"status": before},
                after={"status": case.status.value, "recoveryCaseId": case.id},
            ),
            events=[
                DomainEvent(
                    name=f"auth.{case.kind.value}_completed",
                    aggregate_type="user",
                    aggregate_id=user.id,
                    payload={"recoveryCaseId": case.id},
                )
            ],
        )

    async def _handle_account_closure_request(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, RequestAccountClosure)
        user = await self._current_user(context)
        pin = validation.validate_pin_shape(command.pin)
        matches = self._hasher.verify(pin, user.pin_hash)
        user.verify_pin_for_reauth(matches)

        return CommandResult(
            data={"accepted": True},
            audit=AuditRecord(
                action="auth.account_closure_requested",
                entity_type="user",
                entity_id=user.id,
                after={"username": user.username},
            ),
            events=[
                DomainEvent(
                    name="auth.account_closure_requested",
                    aggregate_type="user",
                    aggregate_id=user.id,
                )
            ],
        )

    async def _handle_revoke_session(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, RevokeSession)
        record = await self._sessions.get(command.session_id)
        if record is None or record.user_id != context.actor.id:
            raise NotFoundError("That session is already gone.")
        record.revoke(self._clock.now())
        await self._sessions.revoke(record, session=session)

        return CommandResult(
            data={"revoked": True},
            audit=AuditRecord(
                action="auth.session_revoked",
                entity_type="session",
                entity_id=record.id,
                after={"userId": record.user_id},
            ),
            events=[
                DomainEvent(
                    name="auth.session_revoked",
                    aggregate_type="session",
                    aggregate_id=record.id,
                )
            ],
        )

    async def get_me(self, user_id: str) -> dict[str, Any]:
        user = await self._users.get(user_id)
        if user is None:
            raise AuthenticationError("Sign in to continue.")
        return user.me_view()

    async def list_sessions(self, user_id: str, current_token: str) -> dict[str, Any]:
        current_hash = hash_token(current_token)
        now = self._clock.now()
        records = await self._sessions.list_live_for_user(user_id, now)
        return {
            "sessions": [
                {
                    "sessionId": record.id,
                    "device": describe_device(record.user_agent),
                    "location": classify_location(record.ip_address),
                    "ipAddress": record.ip_address,
                    "issuedAt": record.issued_at.isoformat(),
                    "isCurrent": record.token_hash == current_hash,
                }
                for record in records
            ]
        }


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
