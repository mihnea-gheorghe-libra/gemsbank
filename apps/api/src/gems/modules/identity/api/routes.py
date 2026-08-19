from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile

from gems.modules.identity.api.schemas import (
    ContactRequest,
    CredentialsRequest,
    VerifyCodeRequest,
)
from gems.modules.identity.application.commands import (
    CompleteOnboarding,
    ResendCode,
    SetContact,
    StartOnboarding,
    SubmitIdentityDocument,
    VerifyCode,
)
from gems.modules.identity.application.onboarding import OnboardingService
from gems.modules.identity.composition import get_onboarding_service
from gems.platform.actors import Actor
from gems.platform.commandbus.bus import bus

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

ServiceDep = Annotated[OnboardingService, Depends(get_onboarding_service)]
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]


def _actor() -> Actor:
    return Actor.public_onboarding()


@router.post("", status_code=201)
async def start(idempotency_key: IdempotencyKey = None) -> dict[str, Any]:
    return await bus.execute(StartOnboarding(), _actor(), idempotency_key)


@router.get("/{kyc_case_id}")
async def read_case(kyc_case_id: str, service: ServiceDep) -> dict[str, Any]:
    return await service.get_case(kyc_case_id)


@router.post("/{kyc_case_id}/document")
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


@router.post("/{kyc_case_id}/contact")
async def set_contact(
    kyc_case_id: str,
    payload: ContactRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = SetContact(kyc_case_id=kyc_case_id, email=payload.email, phone=payload.phone)
    return await bus.execute(command, _actor(), idempotency_key)


@router.post("/{kyc_case_id}/code/resend")
async def resend_code(
    kyc_case_id: str, idempotency_key: IdempotencyKey = None
) -> dict[str, Any]:
    return await bus.execute(ResendCode(kyc_case_id=kyc_case_id), _actor(), idempotency_key)


@router.post("/{kyc_case_id}/code/verify")
async def verify_code(
    kyc_case_id: str,
    payload: VerifyCodeRequest,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = VerifyCode(kyc_case_id=kyc_case_id, code=payload.code.strip())
    return await bus.execute(command, _actor(), idempotency_key)


@router.post("/{kyc_case_id}/complete", status_code=201)
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
