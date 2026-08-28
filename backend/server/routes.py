from datetime import date, datetime, time, timezone
from typing import Annotated, Any

from backend.accounts.account import AccountStatus
from backend.accounts.service import (
    AccountKind,
    AccountsService,
    CloseAccount,
    OpenAccount,
    get_accounts_service,
)
from backend.agents.analytics_service import AnalyticsService, get_analytics_service
from backend.agents.orchestrator_service import (
    OrchestratorService,
    get_orchestrator_service,
)
from backend.agents.payments_service import (
    PaymentsAgentService,
    get_payments_agent_service,
)
from backend.agents.service import SupportService, get_support_service
from backend.agents.synthesis_service import (
    SynthesisService,
    get_synthesis_service,
)
from backend.agents.transcript import sanitise_history
from backend.agents.transcription_service import (
    TranscriptionService,
    get_transcription_service,
)
from backend.auth.service import (
    AuthService,
    RequestAccountClosure,
    RequestEmailChange,
    RequestPasswordChange,
    RequestPasswordReset,
    RequestPhoneChange,
    RequestPinChange,
    RequestUsernameChange,
    ResetPassword,
    RevealPin,
    RevokeSession,
    SignIn,
    SignOut,
    UpdatePreferences,
    VerifyPin,
    VerifyResetCode,
    VerifySecureChange,
    get_auth_service,
)
from backend.capabilities import analytics as analytics_capabilities
from backend.capabilities.education_lessons import load_lessons
from backend.capabilities.service import get_capabilities_service
from backend.cards.service import (
    BlockCardPermanently,
    CardsService,
    FreezeCard,
    IssuePhysicalCard,
    IssueVirtualCard,
    RevealCardDetails,
    RevealCardPin,
    SetAtmLimit,
    SetOnlineLimit,
    UnfreezeCard,
    get_cards_service,
)
from backend.command_bus import bus
from backend.credits.service import (
    CreditsService,
    SubmitCreditApplication,
    WithdrawCreditApplication,
    get_credits_service,
)
from backend.database.mongo import get_db
from backend.deposits.service import (
    CloseTermDeposit,
    CreateTermDeposit,
    TermDepositsService,
    TopUpTermDeposit,
    WithdrawFromTermDeposit,
    get_term_deposits_service,
)
from backend.escalations.service import (
    EscalationsService,
    RequestHandoff,
    get_escalations_service,
)
from backend.exchange.service import (
    ConvertCurrency,
    ExchangeService,
    get_exchange_service,
)
from backend.fx.service import FxInsightsService, get_fx_insights_service
from backend.goals.service import (
    CancelStandingOrder,
    CloseGoal,
    CreateGoal,
    CreateStandingOrder,
    DepositToGoal,
    PauseStandingOrder,
    ResumeStandingOrder,
    WithdrawFromGoal,
    get_goals_service,
)
from backend.helpers.context import Actor
from backend.helpers.errors import AuthenticationError, NotFoundError
from backend.investments.service import (
    BuyInstrument,
    InvestmentsService,
    SellInstrument,
    get_investments_service,
)
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
    AddFunds,
    AddTemplate,
    DeleteTemplate,
    MakeTransfer,
    PaymentsService,
    SignPayment,
    UpdateTemplate,
    get_payments_service,
)
from backend.payments.statement import render_csv, render_pdf
from backend.vendors.service import (
    VendorInsightsService,
    get_vendor_insights_service,
)
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Query,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel, Field


class ContactRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    phone: str = Field(min_length=6, max_length=25)


class VerifyCodeRequest(BaseModel):
    code: str = Field(min_length=4, max_length=8)


class CredentialsRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=200)
    password_confirmation: str = Field(min_length=1, max_length=200, alias="passwordConfirmation")
    pin: str = Field(min_length=4, max_length=8)
    pin_confirmation: str = Field(min_length=4, max_length=8, alias="pinConfirmation")
    prefs: dict[str, Any] | None = None

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


class UsernameChangeRequest(BaseModel):
    new_username: str = Field(min_length=3, max_length=32, alias="newUsername")
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


class PasswordChangeRequest(BaseModel):
    new_password: str = Field(min_length=1, max_length=200, alias="newPassword")
    new_password_confirmation: str = Field(
        min_length=1, max_length=200, alias="newPasswordConfirmation"
    )
    model_config = {"populate_by_name": True}


class VerifySecureChangeRequest(BaseModel):
    code: str = Field(min_length=4, max_length=8)


class AccountClosureRequest(BaseModel):
    pin: str = Field(min_length=4, max_length=8)


class OpenAccountRequest(BaseModel):
    currency: str = Field(min_length=3, max_length=3)
    kind: AccountKind
    label: str | None = Field(default=None, max_length=40)


class ConvertCurrencyRequest(BaseModel):
    source_account_id: str = Field(alias="sourceAccountId", min_length=1, max_length=64)
    target_currency: str = Field(alias="targetCurrency", min_length=3, max_length=3)
    amount_minor: int = Field(alias="amountMinorUnits", gt=0)
    model_config = {"populate_by_name": True}


class TradeInstrumentRequest(BaseModel):
    account_id: str = Field(alias="accountId", min_length=1, max_length=64)
    instrument_id: str = Field(alias="instrumentId", min_length=1, max_length=64)
    amount_minor: int = Field(alias="amountMinorUnits", gt=0)
    model_config = {"populate_by_name": True}


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


class AddFundsRequest(BaseModel):
    account_id: str = Field(alias="accountId", min_length=1, max_length=64)
    amount_minor: int = Field(alias="amountMinorUnits", gt=0)

    model_config = {"populate_by_name": True}


class TemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    beneficiary: str = Field(min_length=2, max_length=70)
    iban: str = Field(min_length=15, max_length=42)
    currency: str = Field(min_length=3, max_length=3)
    reference: str = Field(min_length=1, max_length=140)


class IssueCardRequest(BaseModel):
    account_id: str = Field(alias="accountId")

    model_config = {"populate_by_name": True}


class PreferencesRequest(BaseModel):
    prefs: dict[str, Any]


class LimitRequest(BaseModel):
    limit_minor: int = Field(ge=0, le=5_000_000, alias="limitMinor")
    model_config = {"populate_by_name": True}


class AskAgentRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class ChatTurn(BaseModel):
    role: str = Field(max_length=16)
    content: str = Field(max_length=2000)


class AskOrchestratorRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    screen: str | None = Field(default=None, max_length=32)
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)


class HandoffRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    reason: str | None = Field(default=None, max_length=300)
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)


class GoalRequest(BaseModel):
    parent_account_id: str = Field(alias="parentAccountId", min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=80)
    target_minor: int = Field(alias="targetMinorUnits", gt=0)
    target_date: date = Field(alias="targetDate")
    initial_deposit_minor: int = Field(default=0, alias="initialDepositMinorUnits", ge=0)
    model_config = {"populate_by_name": True}


class GoalMovementRequest(BaseModel):
    amount_minor: int = Field(alias="amountMinorUnits", gt=0)
    model_config = {"populate_by_name": True}


class TermDepositRequest(BaseModel):
    parent_account_id: str = Field(alias="parentAccountId", min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=80)
    term_months: int = Field(alias="termMonths", ge=1, le=360)
    initial_deposit_minor: int = Field(alias="initialDepositMinorUnits", gt=0)
    model_config = {"populate_by_name": True}


class TermDepositMovementRequest(BaseModel):
    amount_minor: int = Field(alias="amountMinorUnits", gt=0)
    model_config = {"populate_by_name": True}


class CreditApplicationRequest(BaseModel):
    product_id: str = Field(alias="productId", min_length=1, max_length=32)
    amount_minor: int = Field(alias="amountMinorUnits", gt=0)
    term_months: int | None = Field(default=None, alias="termMonths", ge=1, le=360)
    purpose: str = Field(default="", max_length=140)
    payout_account_id: str = Field(alias="payoutAccountId", min_length=1, max_length=64)
    model_config = {"populate_by_name": True}


class StandingOrderRequest(BaseModel):
    amount_minor: int = Field(alias="amountMinorUnits", gt=0)
    frequency: str
    created_via: str = Field(default="user", alias="createdVia")
    model_config = {"populate_by_name": True}


class SynthesizeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    language: str | None = None
    voice: str | None = None


ServiceDep = Annotated[OnboardingService, Depends(get_onboarding_service)]
AuthDep = Annotated[AuthService, Depends(get_auth_service)]
AccountsDep = Annotated[AccountsService, Depends(get_accounts_service)]
TermDepositsDep = Annotated[TermDepositsService, Depends(get_term_deposits_service)]
CreditsDep = Annotated[CreditsService, Depends(get_credits_service)]
PaymentsDep = Annotated[PaymentsService, Depends(get_payments_service)]
CardsServiceDep = Annotated[CardsService, Depends(get_cards_service)]
InvestmentsDep = Annotated[InvestmentsService, Depends(get_investments_service)]
VendorInsightsDep = Annotated[
    VendorInsightsService, Depends(get_vendor_insights_service)
]
FxInsightsDep = Annotated[FxInsightsService, Depends(get_fx_insights_service)]
SupportDep = Annotated[SupportService, Depends(get_support_service)]
AnalyticsDep = Annotated[AnalyticsService, Depends(get_analytics_service)]
PaymentsAgentDep = Annotated[PaymentsAgentService, Depends(get_payments_agent_service)]
OrchestratorDep = Annotated[OrchestratorService, Depends(get_orchestrator_service)]
TranscriptionDep = Annotated[
    TranscriptionService, Depends(get_transcription_service)
]
SynthesisDep = Annotated[SynthesisService, Depends(get_synthesis_service)]
EscalationsDep = Annotated[EscalationsService, Depends(get_escalations_service)]
ExchangeDep = Annotated[ExchangeService, Depends(get_exchange_service)]

IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]
BearerToken = Annotated[str | None, Header(alias="Authorization")]

api_router = APIRouter()
onboarding_router = APIRouter(prefix="/onboarding", tags=["onboarding"])
auth_router = APIRouter(prefix="/auth", tags=["auth"])
accounts_router = APIRouter(prefix="/accounts", tags=["accounts"])
payments_router = APIRouter(prefix="/payments", tags=["payments"])
cards_router = APIRouter(prefix="/cards", tags=["cards"])
exchange_router = APIRouter(prefix="/exchange", tags=["exchange"])
investments_router = APIRouter(prefix="/investments", tags=["investments"])
insights_router = APIRouter(prefix="/insights", tags=["insights"])
goals_router = APIRouter(prefix="/goals", tags=["goals"])
deposits_router = APIRouter(prefix="/deposits", tags=["deposits"])
credits_router = APIRouter(prefix="/credits", tags=["credits"])
education_router = APIRouter(prefix="/education", tags=["education"])
agents_router = APIRouter(prefix="/agents", tags=["agents"])


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


async def require_investment_account(actor: CurrentActor, accounts: AccountsDep) -> None:
    owned = await accounts.owned_accounts(actor.id)
    has_investment_account = any(
        account.kind is AccountKind.INVEST and account.status is AccountStatus.ACTIVE
        for account in owned
    )
    if not has_investment_account:
        raise NotFoundError(
            "Open an investment account first.", details={"field": "accountId"}
        )


InvestmentAccountRequired = Annotated[None, Depends(require_investment_account)]
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
    return {
        "commands": bus.registered_commands(),
        "capabilities": [c.describe() for c in get_capabilities_service().all()],
    }


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
        password_confirmation=payload.password_confirmation,
        pin=payload.pin,
        pin_confirmation=payload.pin_confirmation,
        prefs=payload.prefs,
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


@auth_router.post("/pin/verify")
async def verify_pin(
    payload: SignInRequest, idempotency_key: IdempotencyKey = None
) -> dict[str, Any]:
    command = VerifyPin(username=payload.username, pin=payload.pin.strip())
    return await bus.execute(command, _auth_actor(), idempotency_key)


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


@auth_router.post("/username/change", status_code=201)
async def request_username_change(
    actor: CurrentActor,
    payload: UsernameChangeRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = RequestUsernameChange(new_username=payload.new_username)
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


@auth_router.post("/password/change", status_code=201)
async def request_password_change(
    actor: CurrentActor,
    payload: PasswordChangeRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = RequestPasswordChange(
        new_password=payload.new_password,
        new_password_confirmation=payload.new_password_confirmation,
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


@auth_router.put("/preferences")
async def update_preferences(
    actor: CurrentActor,
    payload: PreferencesRequest,
    idempotency_key: IdempotencyKey = None
) -> dict[str, Any]:
    command = UpdatePreferences(user_id=actor.id, prefs=payload.prefs)
    return await bus.execute(command, actor, idempotency_key)


@accounts_router.get("")
async def list_accounts(actor: CurrentActor, accounts: AccountsDep) -> dict[str, Any]:
    return {"accounts": await accounts.list_for_user(actor.id)}


@accounts_router.post("", status_code=201)
async def open_account(
    actor: CurrentActor,
    payload: OpenAccountRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = OpenAccount(currency=payload.currency, kind=payload.kind, label=payload.label)
    return await bus.execute(command, actor, idempotency_key)


@accounts_router.post("/{account_id}/close")
async def close_account(
    actor: CurrentActor,
    account_id: str,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    return await bus.execute(CloseAccount(account_id=account_id), actor, idempotency_key)


@exchange_router.get("/rate")
async def exchange_rate(
    actor: CurrentActor,
    exchange: ExchangeDep,
    source: Annotated[str, Query(alias="from", min_length=3, max_length=3)],
    target: Annotated[str, Query(alias="to", min_length=3, max_length=3)],
) -> dict[str, Any]:
    return await exchange.rate(source, target)


@exchange_router.post("/convert", status_code=201)
async def convert_currency(
    actor: CurrentActor,
    payload: ConvertCurrencyRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = ConvertCurrency(
        source_account_id=payload.source_account_id,
        target_currency=payload.target_currency,
        amount_minor=payload.amount_minor,
    )
    return await bus.execute(command, actor, idempotency_key)


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


@payments_router.get("/statement")
async def get_statement(
    actor: CurrentActor,
    payments: PaymentsDep,
    account_id: Annotated[str, Query(alias="accountId", min_length=1, max_length=64)],
    format: Annotated[str, Query(pattern="^(pdf|csv)$")] = "csv",
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> Response:
    from_dt = datetime.combine(date_from, time.min, tzinfo=timezone.utc) if date_from else None
    to_dt = datetime.combine(date_to, time.max, tzinfo=timezone.utc) if date_to else None
    data = await payments.statement_data(actor.id, account_id, from_dt, to_dt)

    if format == "pdf":
        content = render_pdf(data)
        media_type = "application/pdf"
    else:
        content = render_csv(data)
        media_type = "text/csv"

    filename = f"gems-statement-{account_id}.{format}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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


@payments_router.get("/templates")
async def list_templates(actor: CurrentActor, payments: PaymentsDep) -> dict[str, Any]:
    return await payments.list_templates(actor.id)


@payments_router.post("/templates", status_code=201)
async def add_template(
    actor: CurrentActor,
    payload: TemplateRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = AddTemplate(
        name=payload.name,
        beneficiary=payload.beneficiary,
        iban=payload.iban,
        currency=payload.currency,
        reference=payload.reference,
    )
    return await bus.execute(command, actor, idempotency_key)


@payments_router.put("/templates/{template_id}")
async def update_template(
    actor: CurrentActor,
    template_id: str,
    payload: TemplateRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = UpdateTemplate(
        template_id=template_id,
        name=payload.name,
        beneficiary=payload.beneficiary,
        iban=payload.iban,
        currency=payload.currency,
        reference=payload.reference,
    )
    return await bus.execute(command, actor, idempotency_key)


@payments_router.delete("/templates/{template_id}")
async def delete_template(
    actor: CurrentActor,
    template_id: str,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = DeleteTemplate(template_id=template_id)
    return await bus.execute(command, actor, idempotency_key)


@payments_router.post("/add-funds", status_code=201)
async def add_funds(
    actor: CurrentActor,
    payload: AddFundsRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = AddFunds(account_id=payload.account_id, amount_minor=payload.amount_minor)
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
async def list_cards(actor: CurrentActor, service: CardsServiceDep) -> dict[str, Any]:
    return await service.list_cards(actor.id)


@cards_router.post("/virtual", status_code=201)
async def issue_virtual_card(
    actor: CurrentActor, payload: IssueCardRequest, idempotency_key: IdempotencyKey = None
) -> dict[str, Any]:
    command = IssueVirtualCard(account_id=payload.account_id)
    return await bus.execute(command, actor, idempotency_key)


@cards_router.post("/physical", status_code=201)
async def issue_physical_card(
    actor: CurrentActor, payload: IssueCardRequest, idempotency_key: IdempotencyKey = None
) -> dict[str, Any]:
    command = IssuePhysicalCard(account_id=payload.account_id)
    return await bus.execute(command, actor, idempotency_key)


@cards_router.post("/{card_id}/freeze")
async def freeze_card(
    actor: CurrentActor, card_id: str, idempotency_key: IdempotencyKey = None
) -> dict[str, Any]:
    return await bus.execute(FreezeCard(card_id=card_id), actor, idempotency_key)


@cards_router.post("/{card_id}/unfreeze")
async def unfreeze_card(
    actor: CurrentActor, card_id: str, idempotency_key: IdempotencyKey = None
) -> dict[str, Any]:
    return await bus.execute(UnfreezeCard(card_id=card_id), actor, idempotency_key)


@cards_router.post("/{card_id}/block")
async def block_card(
    actor: CurrentActor, card_id: str, idempotency_key: IdempotencyKey = None
) -> dict[str, Any]:
    return await bus.execute(BlockCardPermanently(card_id=card_id), actor, idempotency_key)


@cards_router.post("/{card_id}/pin/reveal")
async def reveal_card_pin(
    actor: CurrentActor, card_id: str, idempotency_key: IdempotencyKey = None
) -> dict[str, Any]:
    return await bus.execute(RevealCardPin(card_id=card_id), actor, idempotency_key)


@cards_router.post("/{card_id}/details/reveal")
async def reveal_card_details(
    actor: CurrentActor, card_id: str, idempotency_key: IdempotencyKey = None
) -> dict[str, Any]:
    return await bus.execute(RevealCardDetails(card_id=card_id), actor, idempotency_key)


@cards_router.post("/{card_id}/limits/atm")
async def set_atm_limit(
    actor: CurrentActor,
    card_id: str,
    payload: LimitRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = SetAtmLimit(card_id=card_id, limit_minor=payload.limit_minor)
    return await bus.execute(command, actor, idempotency_key)


@cards_router.post("/{card_id}/limits/online")
async def set_online_limit(
    actor: CurrentActor,
    card_id: str,
    payload: LimitRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = SetOnlineLimit(card_id=card_id, limit_minor=payload.limit_minor)
    return await bus.execute(command, actor, idempotency_key)


@investments_router.get("/instruments")
async def list_instruments(service: InvestmentsDep) -> dict[str, Any]:
    return service.instruments()


@investments_router.get("/market")
async def market_snapshot(
    service: InvestmentsDep, range: str | None = None, refresh: bool = False
) -> dict[str, Any]:
    return await service.market(range, force=refresh)


@investments_router.get("/portfolio")
async def investments_portfolio(
    actor: CurrentActor, service: InvestmentsDep, _: InvestmentAccountRequired
) -> dict[str, Any]:
    return await service.portfolio(actor.id)


@investments_router.post("/buy", status_code=201)
async def buy_instrument(
    actor: CurrentActor,
    payload: TradeInstrumentRequest,
    _: InvestmentAccountRequired,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = BuyInstrument(
        account_id=payload.account_id,
        instrument_id=payload.instrument_id,
        amount_minor=payload.amount_minor,
    )
    return await bus.execute(command, actor, idempotency_key)


@investments_router.post("/sell", status_code=201)
async def sell_instrument(
    actor: CurrentActor,
    payload: TradeInstrumentRequest,
    _: InvestmentAccountRequired,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = SellInstrument(
        account_id=payload.account_id,
        instrument_id=payload.instrument_id,
        amount_minor=payload.amount_minor,
    )
    return await bus.execute(command, actor, idempotency_key)


@insights_router.get("")
async def list_insights(
    actor: CurrentActor,
    service: VendorInsightsDep,
    fx: FxInsightsDep,
    limit: int | None = None,
) -> dict[str, Any]:
    board = await service.board_for_user(actor.id, limit)
    fx_board = await fx.board_for_user(actor.id, limit)
    return {**board.model_dump(), "fx": fx_board.model_dump()}
@agents_router.post("/support/ask")
async def ask_support(
    actor: CurrentActor, support: SupportDep, payload: AskAgentRequest
) -> dict[str, Any]:
    answer = await support.ask(actor.id, payload.question)
    return {"answer": answer.answer, "capabilitiesUsed": answer.capabilities_used}


@agents_router.post("/analytics/ask")
async def ask_analytics(
    actor: CurrentActor, analytics: AnalyticsDep, payload: AskAgentRequest
) -> dict[str, Any]:
    answer = await analytics.ask(actor.id, payload.question)
    return {"answer": answer.answer, "capabilitiesUsed": answer.capabilities_used}


@agents_router.post("/payments/ask")
async def ask_payments_agent(
    actor: CurrentActor, agent: PaymentsAgentDep, payload: AskAgentRequest
) -> dict[str, Any]:
    answer = await agent.ask(actor.id, payload.question)
    return {
        "answer": answer.answer,
        "capabilitiesUsed": answer.capabilities_used,
        "proposals": answer.proposals,
    }


@agents_router.post("/ask")
async def ask_orchestrator(
    actor: CurrentActor, orchestrator: OrchestratorDep, payload: AskOrchestratorRequest
) -> dict[str, Any]:
    history = sanitise_history([turn.model_dump() for turn in payload.history])
    answer = await orchestrator.ask(
        actor.id, payload.question, history=history, screen=payload.screen
    )
    return {
        "answer": answer.answer,
        "agentsUsed": answer.agents_used,
        "capabilitiesUsed": answer.capabilities_used,
        "proposals": answer.proposals,
        "escalation": {
            "offered": answer.escalated,
            "reason": answer.escalation_reason,
        },
        "runId": answer.run_id,
    }


@agents_router.post("/transcribe")
async def transcribe_voice_input(
    actor: CurrentActor,
    service: TranscriptionDep,
    audio: Annotated[UploadFile, File()],
    language: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    content = await audio.read()
    transcript = await service.transcribe(
        actor.id, content, audio.content_type or "", language
    )
    return {"text": transcript.text}


@agents_router.post("/synthesize")
async def synthesize_speech_output(
    actor: CurrentActor,
    service: SynthesisDep,
    payload: SynthesizeRequest,
) -> Response:
    audio_bytes = await service.synthesize(
        actor.id, payload.text, payload.language, payload.voice
    )
    return Response(content=audio_bytes, media_type="audio/mpeg")


@agents_router.post("/handoff", status_code=201)
async def request_handoff(
    actor: CurrentActor,
    payload: HandoffRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = RequestHandoff(
        question=payload.question,
        reason=payload.reason,
        transcript=[turn.model_dump() for turn in payload.history],
    )
    return await bus.execute(command, actor, idempotency_key)


@agents_router.get("/handoff")
async def list_handoffs(actor: CurrentActor, escalations: EscalationsDep) -> dict[str, Any]:
    return await escalations.list_for_user(actor.id)


@goals_router.post("", status_code=201)
async def create_goal(
    actor: CurrentActor,
    payload: GoalRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = CreateGoal(
        parent_account_id=payload.parent_account_id,
        name=payload.name,
        target_minor=payload.target_minor,
        target_date=payload.target_date,
        initial_deposit_minor=payload.initial_deposit_minor,
    )
    return await bus.execute(command, actor, idempotency_key)


@goals_router.get("")
async def list_goals(actor: CurrentActor) -> dict[str, Any]:
    progress = await get_goals_service().list_active_progress_for_user(actor.subject_id())
    capability = get_capabilities_service().get("analytics.goal_gap.get")
    goals = []
    for item in progress:
        gap = await capability.resolve(
            actor, analytics_capabilities.GoalGapInput(goalId=item.goal.id)
        )
        projection = gap.model_dump(by_alias=True)
        goals.append(
            {
                "goalId": item.goal.id,
                "name": item.goal.name,
                "accountId": item.goal.account_id,
                "parentAccountId": item.goal.parent_account_id,
                "targetMinorUnits": item.goal.target_minor,
                "currency": item.goal.currency,
                "targetDate": item.goal.target_date.isoformat(),
                "createdAt": item.goal.created_at.isoformat(),
                "progressMinorUnits": item.progress_minor,
                "streakWeeks": item.streak_weeks,
                "streakLastWeek": item.streak_last_week,
                "sharedParentAccount": item.goal.uses_shared_parent_account(),
                "requiredMinorUnitsPerMonth": projection.get("requiredMinorUnitsPerMonth"),
                "actualMinorUnitsPerMonth": projection.get("actualMinorUnitsPerMonth"),
                "gapMinorUnitsPerMonth": projection.get("gapMinorUnitsPerMonth"),
                "projectedCompletionDate": projection.get("projectedCompletionDate"),
            }
        )
    return {"goals": goals}


@goals_router.get("/progress")
async def goal_progress(actor: CurrentActor) -> dict[str, Any]:
    capability = get_capabilities_service().get("analytics.goal_gap.get")
    result = await capability.resolve(actor, analytics_capabilities.GoalGapInput())
    return result.model_dump(by_alias=True)


@goals_router.get("/pace")
async def goal_pace(actor: CurrentActor) -> dict[str, Any]:
    capability = get_capabilities_service().get("analytics.goal_pace.get")
    result = await capability.resolve(actor, analytics_capabilities.GoalPaceInput())
    return result.model_dump(by_alias=True)


@goals_router.post("/{goal_id}/close")
async def close_goal(
    actor: CurrentActor,
    goal_id: str,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = CloseGoal(goal_id=goal_id)
    return await bus.execute(command, actor, idempotency_key)


@goals_router.post("/{goal_id}/deposit")
async def deposit_to_goal(
    actor: CurrentActor,
    goal_id: str,
    payload: GoalMovementRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = DepositToGoal(goal_id=goal_id, amount_minor=payload.amount_minor)
    return await bus.execute(command, actor, idempotency_key)


@goals_router.post("/{goal_id}/withdraw")
async def withdraw_from_goal(
    actor: CurrentActor,
    goal_id: str,
    payload: GoalMovementRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = WithdrawFromGoal(goal_id=goal_id, amount_minor=payload.amount_minor)
    return await bus.execute(command, actor, idempotency_key)


@goals_router.get("/{goal_id}/standing-order")
async def get_standing_order(actor: CurrentActor, goal_id: str) -> dict[str, Any]:
    order = await get_goals_service().get_standing_order_for_goal(
        goal_id, actor.subject_id()
    )
    return {"standingOrder": order.public_view() if order else None}


@goals_router.post("/{goal_id}/standing-order")
async def create_standing_order(
    actor: CurrentActor,
    goal_id: str,
    payload: StandingOrderRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = CreateStandingOrder(
        goal_id=goal_id,
        amount_minor=payload.amount_minor,
        frequency=payload.frequency,
        created_via=payload.created_via,
    )
    return await bus.execute(command, actor, idempotency_key)


@goals_router.post("/standing-order/{standing_order_id}/pause")
async def pause_standing_order(
    actor: CurrentActor,
    standing_order_id: str,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = PauseStandingOrder(standing_order_id=standing_order_id)
    return await bus.execute(command, actor, idempotency_key)


@goals_router.post("/standing-order/{standing_order_id}/resume")
async def resume_standing_order(
    actor: CurrentActor,
    standing_order_id: str,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = ResumeStandingOrder(standing_order_id=standing_order_id)
    return await bus.execute(command, actor, idempotency_key)


@education_router.get("/lessons")
async def list_lessons() -> dict[str, Any]:
    return {
        "lessons": [
            {
                "id": lesson.id,
                "titleEn": lesson.title_en,
                "titleRo": lesson.title_ro,
                "bodyEn": lesson.body_en,
                "bodyRo": lesson.body_ro,
                "questions": [
                    {
                        "id": question.id,
                        "promptEn": question.prompt_en,
                        "promptRo": question.prompt_ro,
                        "options": [
                            {
                                "id": option.id,
                                "labelEn": option.label_en,
                                "labelRo": option.label_ro,
                            }
                            for option in question.options
                        ],
                        "correctOptionId": question.correct_option_id,
                        "explanationEn": question.explanation_en,
                        "explanationRo": question.explanation_ro,
                    }
                    for question in lesson.questions
                ],
            }
            for lesson in load_lessons()
        ]
    }


@goals_router.post("/standing-order/{standing_order_id}/cancel")
async def cancel_standing_order(
    actor: CurrentActor,
    standing_order_id: str,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = CancelStandingOrder(standing_order_id=standing_order_id)
    return await bus.execute(command, actor, idempotency_key)


@deposits_router.get("")
async def list_term_deposits(actor: CurrentActor, deposits: TermDepositsDep) -> dict[str, Any]:
    return {"deposits": await deposits.list_for_user(actor.subject_id())}


@deposits_router.post("", status_code=201)
async def create_term_deposit(
    actor: CurrentActor,
    payload: TermDepositRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = CreateTermDeposit(
        parent_account_id=payload.parent_account_id,
        name=payload.name,
        term_months=payload.term_months,
        initial_deposit_minor=payload.initial_deposit_minor,
    )
    return await bus.execute(command, actor, idempotency_key)


@deposits_router.post("/{deposit_id}/topup")
async def topup_term_deposit(
    actor: CurrentActor,
    deposit_id: str,
    payload: TermDepositMovementRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = TopUpTermDeposit(deposit_id=deposit_id, amount_minor=payload.amount_minor)
    return await bus.execute(command, actor, idempotency_key)


@deposits_router.post("/{deposit_id}/withdraw")
async def withdraw_from_term_deposit(
    actor: CurrentActor,
    deposit_id: str,
    payload: TermDepositMovementRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = WithdrawFromTermDeposit(deposit_id=deposit_id, amount_minor=payload.amount_minor)
    return await bus.execute(command, actor, idempotency_key)


@deposits_router.post("/{deposit_id}/close")
async def close_term_deposit(
    actor: CurrentActor,
    deposit_id: str,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    return await bus.execute(CloseTermDeposit(deposit_id=deposit_id), actor, idempotency_key)


@credits_router.get("/applications")
async def list_credit_applications(actor: CurrentActor, credits: CreditsDep) -> dict[str, Any]:
    return {"applications": await credits.list_for_user(actor.subject_id())}


@credits_router.post("/applications", status_code=201)
async def submit_credit_application(
    actor: CurrentActor,
    payload: CreditApplicationRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = SubmitCreditApplication(
        product_id=payload.product_id,
        amount_minor=payload.amount_minor,
        term_months=payload.term_months,
        purpose=payload.purpose,
        payout_account_id=payload.payout_account_id,
    )
    return await bus.execute(command, actor, idempotency_key)


@credits_router.post("/applications/{application_id}/withdraw")
async def withdraw_credit_application(
    actor: CurrentActor,
    application_id: str,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = WithdrawCreditApplication(application_id=application_id)
    return await bus.execute(command, actor, idempotency_key)


api_router.include_router(onboarding_router)
api_router.include_router(auth_router)
api_router.include_router(accounts_router)
api_router.include_router(payments_router)
api_router.include_router(cards_router)
api_router.include_router(investments_router)
api_router.include_router(insights_router)
api_router.include_router(goals_router)
api_router.include_router(deposits_router)
api_router.include_router(credits_router)
api_router.include_router(education_router)
api_router.include_router(agents_router)
api_router.include_router(exchange_router)
