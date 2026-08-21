from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, UploadFile
from pydantic import BaseModel, Field

from backend.accounts.service import AccountsService, get_accounts_service
from backend.auth.service import (
    AuthService,
    RequestAccountClosure,
    RequestEmailChange,
    RequestPasswordReset,
    RequestPhoneChange,
    RequestPinChange,
    ResetPassword,
    RevealPin,
    RevokeSession,
    SignIn,
    SignOut,
    VerifyResetCode,
    VerifySecureChange,
    get_auth_service,
)
from backend.cards.service import (
    BlockCardPermanently,
    CardsService,
    FreezeCard,
    IssueVirtualCard,
    RevealCardDetails,
    RevealCardPin,
    SetAtmLimit,
    SetOnlineLimit,
    UnfreezeCard,
    get_cards_service,
)
from backend.command_bus import bus
from backend.database.mongo import get_db
from backend.helpers.context import Actor
from backend.helpers.errors import AuthenticationError
from backend.onboarding.service import (
    CompleteOnboarding,
    OnboardingService,
    ResendCode,
    SetContact,
    StartOnboarding,
    SubmitIdentityDocument,
    VerifyCode,
    get_onboarding_service,
)
from backend.payments.service import (
    AddBeneficiary,
    MakeTransfer,
    PaymentsService,
    SignPayment,
    get_payments_service,
)


class ContactRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    phone: str = Field(min_length=6, max_length=25)


class VerifyCodeRequest(BaseModel):
    code: str = Field(min_length=4, max_length=8)


class CredentialsRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=200)
    pin: str = Field(min_length=4, max_length=8)
    pin_confirmation: str = Field(min_length=4, max_length=8, alias="pinConfirmation")

    model_config = {"populate_by_name": True}


class SignInRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    pin: str = Field(min_length=4, max_length=8)


class RevealPinRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=200)


class PasswordResetRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)


class NewPasswordRequest(BaseModel):
    password: str = Field(min_length=1, max_length=200)
    password_confirmation: str = Field(
        min_length=1, max_length=200, alias="passwordConfirmation"
    )

    model_config = {"populate_by_name": True}


class EmailChangeRequest(BaseModel):
    new_email: str = Field(min_length=3, max_length=254, alias="newEmail")
    model_config = {"populate_by_name": True}


class PhoneChangeRequest(BaseModel):
    new_phone: str = Field(min_length=6, max_length=25, alias="newPhone")
    model_config = {"populate_by_name": True}


class PinChangeRequest(BaseModel):
    new_pin: str = Field(min_length=4, max_length=8, alias="newPin")
    new_pin_confirmation: str = Field(min_length=4, max_length=8, alias="newPinConfirmation")
    model_config = {"populate_by_name": True}


class VerifySecureChangeRequest(BaseModel):
    code: str = Field(min_length=4, max_length=8)


class AccountClosureRequest(BaseModel):
    pin: str = Field(min_length=4, max_length=8)


class TransferRequest(BaseModel):
    source_account_id: str = Field(alias="sourceAccountId", min_length=1, max_length=64)
    target_account_id: str | None = Field(default=None, alias="targetAccountId", max_length=64)
    iban: str | None = Field(default=None, max_length=42)
    counterparty: str = Field(min_length=2, max_length=70)
    amount_minor: int = Field(alias="amountMinorUnits", gt=0)
    reference: str = Field(min_length=1, max_length=140)
    category: str | None = Field(default=None, max_length=32)
    acknowledge_payee_mismatch: bool = Field(
        default=False, alias="acknowledgePayeeMismatch"
    )
    model_config = {"populate_by_name": True}


class SignPaymentRequest(BaseModel):
    code: str = Field(min_length=4, max_length=8)


class BeneficiaryRequest(BaseModel):
    name: str = Field(min_length=2, max_length=70)
    iban: str = Field(min_length=15, max_length=42)


class UsernameRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)


class LimitRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    limit_minor: int = Field(ge=0, le=5_000_000, alias="limitMinor")
    model_config = {"populate_by_name": True}


ServiceDep = Annotated[OnboardingService, Depends(get_onboarding_service)]
AuthDep = Annotated[AuthService, Depends(get_auth_service)]
AccountsDep = Annotated[AccountsService, Depends(get_accounts_service)]
PaymentsDep = Annotated[PaymentsService, Depends(get_payments_service)]
CardsServiceDep = Annotated[CardsService, Depends(get_cards_service)]
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]
BearerToken = Annotated[str | None, Header(alias="Authorization")]

api_router = APIRouter()
onboarding_router = APIRouter(prefix="/onboarding", tags=["onboarding"])
auth_router = APIRouter(prefix="/auth", tags=["auth"])
accounts_router = APIRouter(prefix="/accounts", tags=["accounts"])
payments_router = APIRouter(prefix="/payments", tags=["payments"])
cards_router = APIRouter(prefix="/cards", tags=["cards"])


def _actor() -> Actor:
    return Actor.public_onboarding()


def _auth_actor() -> Actor:
    return Actor.public_auth()


def bearer_token(authorization: BearerToken = None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("Sign in to continue.")
    return token.strip()


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def client_user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


async def current_actor(
    auth: AuthDep, token: Annotated[str, Depends(bearer_token)]
) -> Actor:
    return await auth.resolve_actor(token)


CurrentActor = Annotated[Actor, Depends(current_actor)]
SessionToken = Annotated[str, Depends(bearer_token)]
ClientIp = Annotated[str | None, Depends(client_ip)]
ClientUserAgent = Annotated[str | None, Depends(client_user_agent)]
def _cards_actor() -> Actor:
    return Actor.public_cards()


@api_router.get("/health", tags=["platform"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@api_router.get("/system/status", tags=["platform"])
async def system_status() -> dict[str, Any]:
    result = await get_db().command("ping")
    return {
        "status": "operational" if result.get("ok") == 1.0 else "degraded",
        "demo": True,
        "notice": "Demo system. No licence, no real funds, no real card data.",
        "incidents": [],
    }


@api_router.get("/capabilities", tags=["platform"])
async def capabilities() -> dict[str, Any]:
    return {"commands": bus.registered_commands()}


@onboarding_router.post("", status_code=201)
async def start(idempotency_key: IdempotencyKey = None) -> dict[str, Any]:
    return await bus.execute(StartOnboarding(), _actor(), idempotency_key)


@onboarding_router.get("/{kyc_case_id}")
async def read_case(kyc_case_id: str, service: ServiceDep) -> dict[str, Any]:
    return await service.get_case(kyc_case_id)


@onboarding_router.post("/{kyc_case_id}/document")
async def submit_document(
    kyc_case_id: str,
    file: Annotated[UploadFile, File()],
    doc_type: Annotated[str, Form(alias="docType")] = "ci_front",
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    content = await file.read()
    command = SubmitIdentityDocument(
        kyc_case_id=kyc_case_id,
        doc_type=doc_type,
        filename=file.filename or "upload",
        content=content,
    )
    return await bus.execute(command, _actor(), idempotency_key)


@onboarding_router.post("/{kyc_case_id}/contact")
async def set_contact(
    kyc_case_id: str,
    payload: ContactRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = SetContact(kyc_case_id=kyc_case_id, email=payload.email, phone=payload.phone)
    return await bus.execute(command, _actor(), idempotency_key)


@onboarding_router.post("/{kyc_case_id}/code/resend")
async def resend_code(kyc_case_id: str, idempotency_key: IdempotencyKey = None) -> dict[str, Any]:
    return await bus.execute(ResendCode(kyc_case_id=kyc_case_id), _actor(), idempotency_key)


@onboarding_router.post("/{kyc_case_id}/code/verify")
async def verify_code(
    kyc_case_id: str,
    payload: VerifyCodeRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = VerifyCode(kyc_case_id=kyc_case_id, code=payload.code.strip())
    return await bus.execute(command, _actor(), idempotency_key)


@onboarding_router.post("/{kyc_case_id}/complete", status_code=201)
async def complete(
    kyc_case_id: str,
    payload: CredentialsRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = CompleteOnboarding(
        kyc_case_id=kyc_case_id,
        username=payload.username,
        password=payload.password,
        pin=payload.pin,
        pin_confirmation=payload.pin_confirmation,
    )
    return await bus.execute(command, _actor(), idempotency_key)


@auth_router.post("/login")
async def login(
    payload: SignInRequest,
    ip: ClientIp,
    user_agent: ClientUserAgent,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = SignIn(username=payload.username, pin=payload.pin.strip())
    return await bus.execute(command, _auth_actor(), idempotency_key, ip=ip, user_agent=user_agent)


@auth_router.post("/pin/reveal")
async def reveal_pin(
    payload: RevealPinRequest,
    ip: ClientIp,
    user_agent: ClientUserAgent,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = RevealPin(username=payload.username, password=payload.password)
    return await bus.execute(command, _auth_actor(), idempotency_key, ip=ip, user_agent=user_agent)


@auth_router.post("/password/reset", status_code=201)
async def request_password_reset(
    payload: PasswordResetRequest, idempotency_key: IdempotencyKey = None
) -> dict[str, Any]:
    command = RequestPasswordReset(username=payload.username)
    return await bus.execute(command, _auth_actor(), idempotency_key)


@auth_router.post("/password/reset/{recovery_case_id}/verify")
async def verify_reset_code(
    recovery_case_id: str,
    payload: VerifyCodeRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = VerifyResetCode(recovery_case_id=recovery_case_id, code=payload.code.strip())
    return await bus.execute(command, _auth_actor(), idempotency_key)


@auth_router.post("/password/reset/{recovery_case_id}/complete")
async def complete_password_reset(
    recovery_case_id: str,
    payload: NewPasswordRequest,
    ip: ClientIp,
    user_agent: ClientUserAgent,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = ResetPassword(
        recovery_case_id=recovery_case_id,
        password=payload.password,
        password_confirmation=payload.password_confirmation,
    )
    return await bus.execute(command, _auth_actor(), idempotency_key, ip=ip, user_agent=user_agent)


@auth_router.post("/logout")
async def logout(
    token: SessionToken, idempotency_key: IdempotencyKey = None
) -> dict[str, Any]:
    return await bus.execute(SignOut(session_token=token), _auth_actor(), idempotency_key)


@auth_router.get("/me")
async def me(actor: CurrentActor, auth: AuthDep) -> dict[str, Any]:
    return await auth.get_me(actor.id)


@auth_router.get("/sessions")
async def list_sessions(
    actor: CurrentActor, auth: AuthDep, token: SessionToken
) -> dict[str, Any]:
    return await auth.list_sessions(actor.id, token)


@auth_router.post("/sessions/{session_id}/revoke")
async def revoke_session(
    actor: CurrentActor,
    session_id: str,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = RevokeSession(session_id=session_id)
    return await bus.execute(command, actor, idempotency_key)


@auth_router.post("/email/change", status_code=201)
async def request_email_change(
    actor: CurrentActor,
    payload: EmailChangeRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = RequestEmailChange(new_email=payload.new_email)
    return await bus.execute(command, actor, idempotency_key)


@auth_router.post("/phone/change", status_code=201)
async def request_phone_change(
    actor: CurrentActor,
    payload: PhoneChangeRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = RequestPhoneChange(new_phone=payload.new_phone)
    return await bus.execute(command, actor, idempotency_key)


@auth_router.post("/pin/change", status_code=201)
async def request_pin_change(
    actor: CurrentActor,
    payload: PinChangeRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = RequestPinChange(
        new_pin=payload.new_pin, new_pin_confirmation=payload.new_pin_confirmation
    )
    return await bus.execute(command, actor, idempotency_key)


@auth_router.post("/secure-change/{case_id}/verify")
async def verify_secure_change(
    actor: CurrentActor,
    case_id: str,
    payload: VerifySecureChangeRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = VerifySecureChange(case_id=case_id, code=payload.code.strip())
    return await bus.execute(command, actor, idempotency_key)


@auth_router.post("/account/closure-request")
async def request_account_closure(
    actor: CurrentActor,
    payload: AccountClosureRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = RequestAccountClosure(pin=payload.pin.strip())
    return await bus.execute(command, actor, idempotency_key)


@accounts_router.get("")
async def list_accounts(actor: CurrentActor, accounts: AccountsDep) -> dict[str, Any]:
    return {"accounts": await accounts.list_for_user(actor.id)}


@payments_router.get("/summary")
async def payments_summary(actor: CurrentActor, payments: PaymentsDep) -> dict[str, Any]:
    return await payments.summary(actor.id)


@payments_router.get("/transactions")
async def list_transactions(
    actor: CurrentActor,
    payments: PaymentsDep,
    direction: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=70)] = None,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
) -> dict[str, Any]:
    return await payments.list_transactions(
        actor.id, direction=direction, search=search, cursor=cursor, limit=limit
    )


@payments_router.get("/pending")
async def list_pending(actor: CurrentActor, payments: PaymentsDep) -> dict[str, Any]:
    return await payments.list_pending(actor.id)


@payments_router.get("/beneficiaries")
async def list_beneficiaries(actor: CurrentActor, payments: PaymentsDep) -> dict[str, Any]:
    return await payments.list_beneficiaries(actor.id)


@payments_router.post("/beneficiaries", status_code=201)
async def add_beneficiary(
    actor: CurrentActor,
    payload: BeneficiaryRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = AddBeneficiary(name=payload.name, iban=payload.iban)
    return await bus.execute(command, actor, idempotency_key)


@payments_router.post("/transfers", status_code=201)
async def make_transfer(
    actor: CurrentActor,
    payload: TransferRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = MakeTransfer(
        source_account_id=payload.source_account_id,
        target_account_id=payload.target_account_id,
        target_iban=payload.iban,
        counterparty=payload.counterparty,
        amount_minor=payload.amount_minor,
        reference=payload.reference,
        category=payload.category,
        acknowledge_payee_mismatch=payload.acknowledge_payee_mismatch,
    )
    return await bus.execute(command, actor, idempotency_key)


@payments_router.post("/transfers/{payment_id}/sign")
async def sign_transfer(
    actor: CurrentActor,
    payment_id: str,
    payload: SignPaymentRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = SignPayment(payment_id=payment_id, code=payload.code.strip())
    return await bus.execute(command, actor, idempotency_key)
@cards_router.get("")
async def list_cards(username: str, service: CardsServiceDep) -> dict[str, Any]:
    return await service.list_cards(username)


@cards_router.post("/virtual", status_code=201)
async def issue_virtual_card(
    payload: UsernameRequest, idempotency_key: IdempotencyKey = None
) -> dict[str, Any]:
    command = IssueVirtualCard(username=payload.username)
    return await bus.execute(command, _cards_actor(), idempotency_key)


@cards_router.post("/{card_id}/freeze")
async def freeze_card(
    card_id: str, payload: UsernameRequest, idempotency_key: IdempotencyKey = None
) -> dict[str, Any]:
    command = FreezeCard(username=payload.username, card_id=card_id)
    return await bus.execute(command, _cards_actor(), idempotency_key)


@cards_router.post("/{card_id}/unfreeze")
async def unfreeze_card(
    card_id: str, payload: UsernameRequest, idempotency_key: IdempotencyKey = None
) -> dict[str, Any]:
    command = UnfreezeCard(username=payload.username, card_id=card_id)
    return await bus.execute(command, _cards_actor(), idempotency_key)


@cards_router.post("/{card_id}/block")
async def block_card(
    card_id: str, payload: UsernameRequest, idempotency_key: IdempotencyKey = None
) -> dict[str, Any]:
    command = BlockCardPermanently(username=payload.username, card_id=card_id)
    return await bus.execute(command, _cards_actor(), idempotency_key)


@cards_router.post("/{card_id}/pin/reveal")
async def reveal_card_pin(
    card_id: str, payload: UsernameRequest, idempotency_key: IdempotencyKey = None
) -> dict[str, Any]:
    command = RevealCardPin(username=payload.username, card_id=card_id)
    return await bus.execute(command, _cards_actor(), idempotency_key)


@cards_router.post("/{card_id}/details/reveal")
async def reveal_card_details(
    card_id: str, payload: UsernameRequest, idempotency_key: IdempotencyKey = None
) -> dict[str, Any]:
    command = RevealCardDetails(username=payload.username, card_id=card_id)
    return await bus.execute(command, _cards_actor(), idempotency_key)


@cards_router.post("/{card_id}/limits/atm")
async def set_atm_limit(
    card_id: str, payload: LimitRequest, idempotency_key: IdempotencyKey = None
) -> dict[str, Any]:
    command = SetAtmLimit(username=payload.username, card_id=card_id, limit_minor=payload.limit_minor)
    return await bus.execute(command, _cards_actor(), idempotency_key)


@cards_router.post("/{card_id}/limits/online")
async def set_online_limit(
    card_id: str, payload: LimitRequest, idempotency_key: IdempotencyKey = None
) -> dict[str, Any]:
    command = SetOnlineLimit(
        username=payload.username, card_id=card_id, limit_minor=payload.limit_minor
    )
    return await bus.execute(command, _cards_actor(), idempotency_key)


api_router.include_router(onboarding_router)
api_router.include_router(auth_router)
api_router.include_router(accounts_router)
api_router.include_router(payments_router)
api_router.include_router(cards_router)
