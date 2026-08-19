from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile
from pydantic import BaseModel, Field

from backend.command_bus import bus
from backend.database.mongo import get_db
from backend.helpers.context import Actor
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


ServiceDep = Annotated[OnboardingService, Depends(get_onboarding_service)]
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]

api_router = APIRouter()
onboarding_router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def _actor() -> Actor:
    return Actor.public_onboarding()


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


api_router.include_router(onboarding_router)
