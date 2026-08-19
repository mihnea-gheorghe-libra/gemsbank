from datetime import date, datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClientSession
from pymongo.errors import DuplicateKeyError

from gems.modules.identity.domain.kyc import (
    Contact,
    ExtractedIdentity,
    KycCase,
    OnboardingStatus,
    OtpChallenge,
    SubmittedDocument,
)
from gems.platform.db.collections import kyc_cases_collection, users_collection
from gems.platform.errors import ConflictError


def _document_to_bson(document: SubmittedDocument | None) -> dict[str, Any] | None:
    if document is None:
        return None
    return {
        "docRef": document.doc_ref,
        "docType": document.doc_type,
        "extracted": {
            "fullName": document.extracted.full_name,
            "birthDate": document.extracted.birth_date.isoformat(),
            "cnpMasked": document.extracted.cnp_masked,
            "documentNumberMasked": document.extracted.document_number_masked,
            "expiresOn": document.extracted.expires_on.isoformat(),
        },
        "submittedAt": document.submitted_at,
    }


def _document_from_bson(raw: dict[str, Any] | None) -> SubmittedDocument | None:
    if raw is None:
        return None
    extracted = raw["extracted"]
    return SubmittedDocument(
        doc_ref=raw["docRef"],
        doc_type=raw["docType"],
        extracted=ExtractedIdentity(
            full_name=extracted["fullName"],
            birth_date=date.fromisoformat(extracted["birthDate"]),
            cnp_masked=extracted["cnpMasked"],
            document_number_masked=extracted["documentNumberMasked"],
            expires_on=date.fromisoformat(extracted["expiresOn"]),
        ),
        submitted_at=raw["submittedAt"],
    )


def _otp_to_bson(otp: OtpChallenge | None) -> dict[str, Any] | None:
    if otp is None:
        return None
    return {
        "codeHash": otp.code_hash,
        "expiresAt": otp.expires_at,
        "sentAt": otp.sent_at,
        "attempts": otp.attempts,
        "resends": otp.resends,
    }


def _otp_from_bson(raw: dict[str, Any] | None) -> OtpChallenge | None:
    if raw is None:
        return None
    return OtpChallenge(
        code_hash=raw["codeHash"],
        expires_at=raw["expiresAt"],
        sent_at=raw["sentAt"],
        attempts=raw["attempts"],
        resends=raw["resends"],
    )


def _to_bson(case: KycCase) -> dict[str, Any]:
    return {
        "_id": case.id,
        "status": case.status.value,
        "document": _document_to_bson(case.document),
        "contact": {"email": case.contact.email, "phone": case.contact.phone}
        if case.contact
        else None,
        "otp": _otp_to_bson(case.otp),
        "userId": case.user_id,
        "createdAt": case.created_at,
        "updatedAt": case.updated_at,
    }


def _from_bson(raw: dict[str, Any]) -> KycCase:
    contact = raw.get("contact")
    return KycCase(
        id=raw["_id"],
        status=OnboardingStatus(raw["status"]),
        document=_document_from_bson(raw.get("document")),
        contact=Contact(email=contact["email"], phone=contact["phone"]) if contact else None,
        otp=_otp_from_bson(raw.get("otp")),
        user_id=raw.get("userId"),
        created_at=raw["createdAt"],
        updated_at=raw["updatedAt"],
    )


class MongoKycCaseRepository:
    async def add(self, case: KycCase, session: AsyncIOMotorClientSession | None = None) -> None:
        await kyc_cases_collection().insert_one(_to_bson(case), session=session)

    async def get(self, case_id: str) -> KycCase | None:
        raw = await kyc_cases_collection().find_one({"_id": case_id})
        return _from_bson(raw) if raw else None

    async def save(self, case: KycCase, session: AsyncIOMotorClientSession | None = None) -> None:
        payload = _to_bson(case)
        payload.pop("_id")
        await kyc_cases_collection().update_one(
            {"_id": case.id}, {"$set": payload}, session=session
        )


class MongoUserRepository:
    async def create(
        self,
        user_id: str,
        username: str,
        email: str,
        phone: str,
        password_hash: str,
        pin_hash: str,
        kyc_case_id: str,
        session: AsyncIOMotorClientSession | None = None,
    ) -> None:
        payload = {
            "_id": user_id,
            "username": username,
            "email": email,
            "phone": phone,
            "passwordHash": password_hash,
            "pinHash": pin_hash,
            "kycCaseId": kyc_case_id,
            "prefs": {"lang": "ro", "theme": "light", "tts": False, "hideBalances": True},
            "status": "active",
            "createdAt": datetime.now(timezone.utc),
        }
        try:
            await users_collection().insert_one(payload, session=session)
        except DuplicateKeyError as exc:
            field = "username" if "username" in str(exc) else "email"
            raise ConflictError(
                f"That {field} is already registered.", details={"field": field}
            ) from exc

    async def exists_username(self, username: str) -> bool:
        return await users_collection().count_documents({"username": username}, limit=1) > 0

    async def exists_email(self, email: str) -> bool:
        return await users_collection().count_documents({"email": email}, limit=1) > 0
