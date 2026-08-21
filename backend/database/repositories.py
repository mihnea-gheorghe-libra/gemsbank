from datetime import date, datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClientSession
from pymongo.errors import DuplicateKeyError

from backend.auth.credentials import (
    AuthUser,
    RecoveryCase,
    RecoveryStatus,
    ResetChallenge,
)
from backend.cards.card import Card, CardKind, CardState
from backend.database.mongo import (
    cards_collection,
    kyc_cases_collection,
    recovery_cases_collection,
    users_collection,
)
from backend.helpers.errors import ConflictError
from backend.onboarding.kyc import (
    Contact,
    ExtractedIdentity,
    KycCase,
    OnboardingStatus,
    OtpChallenge,
    SubmittedDocument,
)


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
        pin_encrypted: str,
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
            "pinEncrypted": pin_encrypted,
            "kycCaseId": kyc_case_id,
            "prefs": {"lang": "ro", "theme": "light", "tts": False, "hideBalances": True},
            "pin": {"failures": 0, "locked": False},
            "password": {"failures": 0, "lockoutStage": 0, "lockedUntil": None},
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


def _auth_user_from_bson(raw: dict[str, Any]) -> AuthUser:
    pin = raw.get("pin") or {}
    password = raw.get("password") or {}
    return AuthUser(
        id=raw["_id"],
        username=raw["username"],
        email=raw["email"],
        password_hash=raw["passwordHash"],
        pin_hash=raw["pinHash"],
        pin_encrypted=raw.get("pinEncrypted"),
        status=raw.get("status", "active"),
        pin_failures=pin.get("failures", 0),
        pin_locked=pin.get("locked", False),
        password_failures=password.get("failures", 0),
        password_lockout_stage=password.get("lockoutStage", 0),
        password_locked_until=password.get("lockedUntil"),
    )


class MongoAuthUserRepository:
    async def get_by_username(self, username: str) -> AuthUser | None:
        raw = await users_collection().find_one({"username": username})
        return _auth_user_from_bson(raw) if raw else None

    async def get(self, user_id: str) -> AuthUser | None:
        raw = await users_collection().find_one({"_id": user_id})
        return _auth_user_from_bson(raw) if raw else None

    async def save(
        self, user: AuthUser, session: AsyncIOMotorClientSession | None = None
    ) -> None:
        await users_collection().update_one(
            {"_id": user.id},
            {
                "$set": {
                    "passwordHash": user.password_hash,
                    "status": user.status,
                    "pin": {"failures": user.pin_failures, "locked": user.pin_locked},
                    "password": {
                        "failures": user.password_failures,
                        "lockoutStage": user.password_lockout_stage,
                        "lockedUntil": user.password_locked_until,
                    },
                }
            },
            session=session,
        )


def _challenge_to_bson(otp: ResetChallenge | None) -> dict[str, Any] | None:
    if otp is None:
        return None
    return {
        "codeHash": otp.code_hash,
        "expiresAt": otp.expires_at,
        "sentAt": otp.sent_at,
        "attempts": otp.attempts,
    }


def _challenge_from_bson(raw: dict[str, Any] | None) -> ResetChallenge | None:
    if raw is None:
        return None
    return ResetChallenge(
        code_hash=raw["codeHash"],
        expires_at=raw["expiresAt"],
        sent_at=raw["sentAt"],
        attempts=raw["attempts"],
    )


def _recovery_to_bson(case: RecoveryCase) -> dict[str, Any]:
    return {
        "_id": case.id,
        "userId": case.user_id,
        "kind": "password_reset",
        "status": case.status.value,
        "otp": _challenge_to_bson(case.otp),
        "createdAt": case.created_at,
        "updatedAt": case.updated_at,
    }


def _recovery_from_bson(raw: dict[str, Any]) -> RecoveryCase:
    return RecoveryCase(
        id=raw["_id"],
        user_id=raw["userId"],
        status=RecoveryStatus(raw["status"]),
        otp=_challenge_from_bson(raw.get("otp")),
        created_at=raw["createdAt"],
        updated_at=raw["updatedAt"],
    )


class MongoRecoveryCaseRepository:
    async def add(
        self, case: RecoveryCase, session: AsyncIOMotorClientSession | None = None
    ) -> None:
        await recovery_cases_collection().insert_one(_recovery_to_bson(case), session=session)

    async def get(self, case_id: str) -> RecoveryCase | None:
        raw = await recovery_cases_collection().find_one({"_id": case_id})
        return _recovery_from_bson(raw) if raw else None

    async def save(
        self, case: RecoveryCase, session: AsyncIOMotorClientSession | None = None
    ) -> None:
        payload = _recovery_to_bson(case)
        payload.pop("_id")
        await recovery_cases_collection().update_one(
            {"_id": case.id}, {"$set": payload}, session=session
        )


def _card_to_bson(card: Card) -> dict[str, Any]:
    return {
        "_id": card.id,
        "userId": card.user_id,
        "kind": card.kind.value,
        "last4": card.last4,
        "ownerName": card.owner_name,
        "currency": card.currency,
        "expiresOn": card.expires_on.isoformat(),
        "state": card.state.value,
        "pinEncrypted": card.pin_encrypted,
        "cvvEncrypted": card.cvv_encrypted,
        "atmLimitMinor": card.atm_limit_minor,
        "onlineLimitMinor": card.online_limit_minor,
        "createdAt": card.created_at,
        "updatedAt": card.updated_at,
    }


def _card_from_bson(raw: dict[str, Any]) -> Card:
    return Card(
        id=raw["_id"],
        user_id=raw["userId"],
        kind=CardKind(raw["kind"]),
        last4=raw["last4"],
        owner_name=raw["ownerName"],
        currency=raw.get("currency", "RON"),
        expires_on=date.fromisoformat(raw["expiresOn"]),
        state=CardState(raw["state"]),
        pin_encrypted=raw["pinEncrypted"],
        cvv_encrypted=raw.get("cvvEncrypted"),
        atm_limit_minor=raw["atmLimitMinor"],
        online_limit_minor=raw["onlineLimitMinor"],
        created_at=raw["createdAt"],
        updated_at=raw["updatedAt"],
    )


class MongoCardRepository:
    async def add(self, card: Card, session: AsyncIOMotorClientSession | None = None) -> None:
        await cards_collection().insert_one(_card_to_bson(card), session=session)

    async def get(self, card_id: str) -> Card | None:
        raw = await cards_collection().find_one({"_id": card_id})
        return _card_from_bson(raw) if raw else None

    async def list_for_user(self, user_id: str) -> list[Card]:
        cursor = cards_collection().find({"userId": user_id}).sort("createdAt", 1)
        return [_card_from_bson(raw) async for raw in cursor]

    async def save(self, card: Card, session: AsyncIOMotorClientSession | None = None) -> None:
        payload = _card_to_bson(card)
        payload.pop("_id")
        await cards_collection().update_one({"_id": card.id}, {"$set": payload}, session=session)
