import re
from datetime import date, datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClientSession
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from backend.accounts.account import Account, AccountKind, AccountStatus
from backend.auth.credentials import (
    AuthUser,
    RecoveryCase,
    RecoveryStatus,
    ResetChallenge,
    Session,
)
from backend.cards.card import Card, CardKind, CardState
from backend.database.mongo import (
    accounts_collection,
    beneficiaries_collection,
    cards_collection,
    journal_collection,
    kyc_cases_collection,
    payments_collection,
    recovery_cases_collection,
    sessions_collection,
    users_collection,
)
from backend.helpers.errors import ConflictError
from backend.ledger.journal import JournalEntry, JournalTransaction, TransactionKind
from backend.onboarding.kyc import (
    Contact,
    ExtractedIdentity,
    KycCase,
    OnboardingStatus,
    OtpChallenge,
    SubmittedDocument,
)
from backend.payments.payment import (
    Beneficiary,
    PayeeVerification,
    Payment,
    PaymentRail,
    PaymentStatus,
    SignatureChallenge,
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
        prefs: dict[str, Any] | None = None,
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
            "prefs": {"lang": "ro", "theme": "light", "tts": False, "hideBalances": True} | (prefs or {}),
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
        prefs=raw.get("prefs", {}),
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
                    "prefs": user.prefs,
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


def _session_to_bson(record: Session) -> dict[str, Any]:
    return {
        "_id": record.id,
        "userId": record.user_id,
        "tokenHash": record.token_hash,
        "issuedAt": record.issued_at,
        "expiresAt": record.expires_at,
        "revokedAt": record.revoked_at,
    }


def _session_from_bson(raw: dict[str, Any]) -> Session:
    return Session(
        id=raw["_id"],
        user_id=raw["userId"],
        token_hash=raw["tokenHash"],
        issued_at=raw["issuedAt"],
        expires_at=raw["expiresAt"],
        revoked_at=raw.get("revokedAt"),
    )


class MongoSessionRepository:
    async def add(
        self, record: Session, session: AsyncIOMotorClientSession | None = None
    ) -> None:
        await sessions_collection().insert_one(_session_to_bson(record), session=session)

    async def get_by_token_hash(self, token_hash: str) -> Session | None:
        raw = await sessions_collection().find_one({"tokenHash": token_hash})
        return _session_from_bson(raw) if raw else None

    async def revoke(
        self, record: Session, session: AsyncIOMotorClientSession | None = None
    ) -> None:
        await sessions_collection().update_one(
            {"_id": record.id}, {"$set": {"revokedAt": record.revoked_at}}, session=session
        )


def _account_to_bson(account: Account) -> dict[str, Any]:
    return {
        "_id": account.id,
        "userId": account.user_id,
        "iban": account.iban,
        "holderName": account.holder_name,
        "currency": account.currency,
        "kind": account.kind.value,
        "label": account.label,
        "status": account.status.value,
        "openedAt": account.opened_at,
    }


def _account_from_bson(raw: dict[str, Any]) -> Account:
    return Account(
        id=raw["_id"],
        user_id=raw["userId"],
        iban=raw["iban"],
        holder_name=raw["holderName"],
        currency=raw["currency"],
        kind=AccountKind(raw["kind"]),
        label=raw["label"],
        status=AccountStatus(raw["status"]),
        opened_at=raw["openedAt"],
    )


class MongoAccountRepository:
    async def add(
        self, account: Account, session: AsyncIOMotorClientSession | None = None
    ) -> None:
        try:
            await accounts_collection().insert_one(_account_to_bson(account), session=session)
        except DuplicateKeyError as exc:
            raise ConflictError(
                "That IBAN is already in use. Try again.", details={"field": "iban"}
            ) from exc

    async def get(self, account_id: str) -> Account | None:
        raw = await accounts_collection().find_one({"_id": account_id})
        return _account_from_bson(raw) if raw else None

    async def get_by_iban(self, iban: str) -> Account | None:
        raw = await accounts_collection().find_one({"iban": iban})
        return _account_from_bson(raw) if raw else None

    async def list_for_user(self, user_id: str) -> list[Account]:
        found = accounts_collection().find({"userId": user_id}).sort("openedAt", ASCENDING)
        return [_account_from_bson(raw) async for raw in found]


def _journal_to_bson(transaction: JournalTransaction) -> dict[str, Any]:
    return {
        "_id": transaction.id,
        "currency": transaction.currency,
        "kind": transaction.kind.value,
        "entries": [
            {"accountId": entry.account_id, "amount": entry.amount}
            for entry in transaction.entries
        ],
        "reference": transaction.reference,
        "counterparty": transaction.counterparty,
        "category": transaction.category,
        "postedAt": transaction.posted_at,
        "correlationId": transaction.correlation_id,
        "actor": transaction.actor,
        "reverses": transaction.reverses,
    }


def _journal_from_bson(raw: dict[str, Any]) -> JournalTransaction:
    return JournalTransaction(
        id=raw["_id"],
        currency=raw["currency"],
        kind=TransactionKind(raw["kind"]),
        entries=[
            JournalEntry(account_id=entry["accountId"], amount=entry["amount"])
            for entry in raw["entries"]
        ],
        reference=raw["reference"],
        counterparty=raw["counterparty"],
        category=raw["category"],
        posted_at=raw["postedAt"],
        correlation_id=raw["correlationId"],
        actor=raw["actor"],
        reverses=raw.get("reverses"),
    )


class MongoJournalRepository:
    async def append(
        self, transaction: JournalTransaction, session: AsyncIOMotorClientSession | None = None
    ) -> None:
        await journal_collection().insert_one(_journal_to_bson(transaction), session=session)

    async def balances_for(self, account_ids: list[str]) -> dict[str, int]:
        pipeline: list[dict[str, Any]] = [
            {"$match": {"entries.accountId": {"$in": account_ids}}},
            {"$unwind": "$entries"},
            {"$match": {"entries.accountId": {"$in": account_ids}}},
            {"$group": {"_id": "$entries.accountId", "total": {"$sum": "$entries.amount"}}},
        ]
        found = journal_collection().aggregate(pipeline)
        return {row["_id"]: int(row["total"]) async for row in found}

    async def debited_since(self, account_ids: list[str], since: datetime) -> int:
        pipeline: list[dict[str, Any]] = [
            {
                "$match": {
                    "entries.accountId": {"$in": account_ids},
                    "postedAt": {"$gte": since},
                }
            },
            {"$unwind": "$entries"},
            {
                "$match": {
                    "entries.accountId": {"$in": account_ids},
                    "entries.amount": {"$lt": 0},
                }
            },
            {"$group": {"_id": None, "total": {"$sum": "$entries.amount"}}},
        ]
        async for row in journal_collection().aggregate(pipeline):
            return abs(int(row["total"]))
        return 0

    async def count_for(self, account_ids: list[str]) -> int:
        pipeline: list[dict[str, Any]] = [
            {"$match": {"entries.accountId": {"$in": account_ids}}},
            {"$unwind": "$entries"},
            {"$match": {"entries.accountId": {"$in": account_ids}}},
            {"$count": "total"},
        ]
        async for row in journal_collection().aggregate(pipeline):
            return int(row["total"])
        return 0

    async def page_for(
        self,
        account_ids: list[str],
        direction: str | None,
        search: str | None,
        cursor: tuple[datetime, str] | None,
        limit: int,
    ) -> list[JournalTransaction]:
        entry_match: dict[str, Any] = {"accountId": {"$in": account_ids}}
        if direction == "credit":
            entry_match["amount"] = {"$gt": 0}
        elif direction == "debit":
            entry_match["amount"] = {"$lt": 0}

        query: dict[str, Any] = {"entries": {"$elemMatch": entry_match}}
        if search:
            pattern = re.escape(search)
            query["$or"] = [
                {"counterparty": {"$regex": pattern, "$options": "i"}},
                {"reference": {"$regex": pattern, "$options": "i"}},
            ]
        if cursor:
            posted_at, transaction_id = cursor
            query["$and"] = [
                {
                    "$or": [
                        {"postedAt": {"$lt": posted_at}},
                        {"postedAt": posted_at, "_id": {"$lt": transaction_id}},
                    ]
                }
            ]

        found = (
            journal_collection()
            .find(query)
            .sort([("postedAt", DESCENDING), ("_id", DESCENDING)])
            .limit(limit)
        )
        return [_journal_from_bson(raw) async for raw in found]


def _signature_to_bson(challenge: SignatureChallenge | None) -> dict[str, Any] | None:
    if challenge is None:
        return None
    return {
        "codeHash": challenge.code_hash,
        "expiresAt": challenge.expires_at,
        "issuedAt": challenge.issued_at,
        "attempts": challenge.attempts,
    }


def _signature_from_bson(raw: dict[str, Any] | None) -> SignatureChallenge | None:
    if raw is None:
        return None
    return SignatureChallenge(
        code_hash=raw["codeHash"],
        expires_at=raw["expiresAt"],
        issued_at=raw["issuedAt"],
        attempts=raw["attempts"],
    )


def _payment_to_bson(payment: Payment) -> dict[str, Any]:
    return {
        "_id": payment.id,
        "userId": payment.user_id,
        "rail": payment.rail.value,
        "status": payment.status.value,
        "sourceAccountId": payment.source_account_id,
        "targetAccountId": payment.target_account_id,
        "targetIban": payment.target_iban,
        "counterparty": payment.counterparty,
        "amountMinorUnits": payment.amount_minor,
        "currency": payment.currency,
        "reference": payment.reference,
        "category": payment.category,
        "payeeCheck": payment.payee_check.value,
        "signature": _signature_to_bson(payment.signature),
        "journalTransactionId": payment.journal_transaction_id,
        "rejectedReason": payment.rejected_reason,
        "createdAt": payment.created_at,
        "updatedAt": payment.updated_at,
    }


def _payment_from_bson(raw: dict[str, Any]) -> Payment:
    return Payment(
        id=raw["_id"],
        user_id=raw["userId"],
        rail=PaymentRail(raw["rail"]),
        status=PaymentStatus(raw["status"]),
        source_account_id=raw["sourceAccountId"],
        target_account_id=raw.get("targetAccountId"),
        target_iban=raw["targetIban"],
        counterparty=raw["counterparty"],
        amount_minor=raw["amountMinorUnits"],
        currency=raw["currency"],
        reference=raw["reference"],
        category=raw["category"],
        payee_check=PayeeVerification(raw["payeeCheck"]),
        signature=_signature_from_bson(raw.get("signature")),
        journal_transaction_id=raw.get("journalTransactionId"),
        rejected_reason=raw.get("rejectedReason"),
        created_at=raw["createdAt"],
        updated_at=raw["updatedAt"],
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


class MongoPaymentRepository:
    async def add(
        self, payment: Payment, session: AsyncIOMotorClientSession | None = None
    ) -> None:
        await payments_collection().insert_one(_payment_to_bson(payment), session=session)

    async def get(self, payment_id: str) -> Payment | None:
        raw = await payments_collection().find_one({"_id": payment_id})
        return _payment_from_bson(raw) if raw else None

    async def save(
        self, payment: Payment, session: AsyncIOMotorClientSession | None = None
    ) -> None:
        payload = _payment_to_bson(payment)
        payload.pop("_id")
        await payments_collection().update_one(
            {"_id": payment.id}, {"$set": payload}, session=session
        )

    async def list_by_status(self, user_id: str, status: PaymentStatus) -> list[Payment]:
        found = (
            payments_collection()
            .find({"userId": user_id, "status": status.value})
            .sort("createdAt", DESCENDING)
        )
        return [_payment_from_bson(raw) async for raw in found]

    async def count_by_status(self, user_id: str, status: PaymentStatus) -> int:
        return await payments_collection().count_documents(
            {"userId": user_id, "status": status.value}
        )


def _beneficiary_to_bson(beneficiary: Beneficiary) -> dict[str, Any]:
    return {
        "_id": beneficiary.id,
        "userId": beneficiary.user_id,
        "name": beneficiary.name,
        "iban": beneficiary.iban,
        "createdAt": beneficiary.created_at,
    }


def _beneficiary_from_bson(raw: dict[str, Any]) -> Beneficiary:
    return Beneficiary(
        id=raw["_id"],
        user_id=raw["userId"],
        name=raw["name"],
        iban=raw["iban"],
        created_at=raw["createdAt"],
    )


class MongoBeneficiaryRepository:
    async def add(
        self, beneficiary: Beneficiary, session: AsyncIOMotorClientSession | None = None
    ) -> None:
        try:
            await beneficiaries_collection().insert_one(
                _beneficiary_to_bson(beneficiary), session=session
            )
        except DuplicateKeyError as exc:
            raise ConflictError(
                "That beneficiary is already saved.", details={"field": "iban"}
            ) from exc

    async def list_for_user(self, user_id: str) -> list[Beneficiary]:
        found = beneficiaries_collection().find({"userId": user_id}).sort("name", ASCENDING)
        return [_beneficiary_from_bson(raw) async for raw in found]

    async def find(self, user_id: str, iban: str) -> Beneficiary | None:
        raw = await beneficiaries_collection().find_one({"userId": user_id, "iban": iban})
        return _beneficiary_from_bson(raw) if raw else None
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
