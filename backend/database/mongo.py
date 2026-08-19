from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from backend.config import settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(
            settings.mongo_uri, uuidRepresentation="standard", tz_aware=True
        )
    return _client


def get_db() -> AsyncIOMotorDatabase:
    return get_client()[settings.mongo_db_name]


async def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


def users_collection() -> AsyncIOMotorCollection:
    return get_db()["users"]


def kyc_cases_collection() -> AsyncIOMotorCollection:
    return get_db()["kycCases"]


def audit_log_collection() -> AsyncIOMotorCollection:
    return get_db()["auditLog"]


def outbox_collection() -> AsyncIOMotorCollection:
    return get_db()["outbox"]


def idempotency_collection() -> AsyncIOMotorCollection:
    return get_db()["idempotencyKeys"]


def accounts_collection() -> AsyncIOMotorCollection:
    return get_db()["accounts"]


def transactions_collection() -> AsyncIOMotorCollection:
    return get_db()["transactions"]


async def ensure_indexes() -> None:
    await users_collection().create_index([("username", ASCENDING)], unique=True, name="uq_username")
    await users_collection().create_index([("email", ASCENDING)], unique=True, name="uq_email")

    await kyc_cases_collection().create_index([("status", ASCENDING)], name="ix_status")
    await kyc_cases_collection().create_index([("createdAt", DESCENDING)], name="ix_created")

    await idempotency_collection().create_index(
        [("key", ASCENDING), ("scope", ASCENDING)], unique=True, name="uq_key_scope"
    )
    await idempotency_collection().create_index(
        [("createdAt", ASCENDING)], expireAfterSeconds=86400, name="ttl_created"
    )

    await audit_log_collection().create_index([("ts", DESCENDING)], name="ix_ts")
    await audit_log_collection().create_index(
        [("entityType", ASCENDING), ("entityId", ASCENDING)], name="ix_entity"
    )
    await audit_log_collection().create_index([("correlationId", ASCENDING)], name="ix_correlation")

    await outbox_collection().create_index(
        [("dispatchedAt", ASCENDING), ("occurredAt", ASCENDING)], name="ix_undispatched"
    )
