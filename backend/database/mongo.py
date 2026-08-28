from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorCollection,
    AsyncIOMotorDatabase,
)
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


def recovery_cases_collection() -> AsyncIOMotorCollection:
    return get_db()["recoveryCases"]


def audit_log_collection() -> AsyncIOMotorCollection:
    return get_db()["auditLog"]


def outbox_collection() -> AsyncIOMotorCollection:
    return get_db()["outbox"]


def idempotency_collection() -> AsyncIOMotorCollection:
    return get_db()["idempotencyKeys"]


def sessions_collection() -> AsyncIOMotorCollection:
    return get_db()["sessions"]


def accounts_collection() -> AsyncIOMotorCollection:
    return get_db()["accounts"]


def journal_collection() -> AsyncIOMotorCollection:
    return get_db()["journalTransactions"]


def payments_collection() -> AsyncIOMotorCollection:
    return get_db()["payments"]


def beneficiaries_collection() -> AsyncIOMotorCollection:
    return get_db()["beneficiaries"]


def payment_templates_collection() -> AsyncIOMotorCollection:
    return get_db()["paymentTemplates"]


def cards_collection() -> AsyncIOMotorCollection:
    return get_db()["cards"]


def goals_collection() -> AsyncIOMotorCollection:
    return get_db()["goals"]


def standing_orders_collection() -> AsyncIOMotorCollection:
    return get_db()["standingOrders"]


def handoffs_collection() -> AsyncIOMotorCollection:
    return get_db()["supportHandoffs"]


async def _drop_unique_indexes(collection: AsyncIOMotorCollection) -> None:
    for name, spec in (await collection.index_information()).items():
        if name != "_id_" and spec.get("unique"):
            await collection.drop_index(name)


async def ensure_indexes() -> None:
    await users_collection().create_index([("username", ASCENDING)], unique=True, name="uq_username")
    await users_collection().create_index([("email", ASCENDING)], unique=True, name="uq_email")

    await kyc_cases_collection().create_index([("status", ASCENDING)], name="ix_status")
    await kyc_cases_collection().create_index([("createdAt", DESCENDING)], name="ix_created")

    await recovery_cases_collection().create_index([("userId", ASCENDING)], name="ix_user")
    await recovery_cases_collection().create_index([("createdAt", DESCENDING)], name="ix_created")

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

    await sessions_collection().create_index(
        [("tokenHash", ASCENDING)], unique=True, name="uq_token"
    )
    await sessions_collection().create_index([("userId", ASCENDING)], name="ix_user")
    await sessions_collection().create_index(
        [("expiresAt", ASCENDING)], expireAfterSeconds=0, name="ttl_expires"
    )

    await accounts_collection().create_index([("iban", ASCENDING)], unique=True, name="uq_iban")
    await accounts_collection().create_index(
        [("userId", ASCENDING), ("openedAt", ASCENDING)], name="ix_user_opened"
    )

    await journal_collection().create_index(
        [("entries.accountId", ASCENDING), ("postedAt", DESCENDING)], name="ix_account_posted"
    )
    await journal_collection().create_index(
        [("postedAt", DESCENDING), ("_id", DESCENDING)], name="ix_cursor"
    )
    await journal_collection().create_index(
        [("correlationId", ASCENDING)], name="ix_correlation"
    )

    await payments_collection().create_index(
        [("userId", ASCENDING), ("status", ASCENDING), ("createdAt", DESCENDING)],
        name="ix_user_status",
    )
    await payments_collection().create_index(
        [("journalTransactionId", ASCENDING)], name="ix_journal"
    )

    await beneficiaries_collection().create_index(
        [("userId", ASCENDING), ("iban", ASCENDING)], unique=True, name="uq_user_iban"
    )
    await payment_templates_collection().create_index(
        [("userId", ASCENDING), ("createdAt", ASCENDING)], name="ix_user_created"
    )
    await handoffs_collection().create_index(
        [("userId", ASCENDING), ("createdAt", DESCENDING)], name="ix_user_created"
    )
    await handoffs_collection().create_index([("status", ASCENDING)], name="ix_status")

    await cards_collection().create_index([("userId", ASCENDING)], name="ix_user")
    await cards_collection().create_index([("createdAt", ASCENDING)], name="ix_created")

    await _drop_unique_indexes(goals_collection())
    await goals_collection().create_index(
        [("userId", ASCENDING), ("status", ASCENDING)], name="ix_user_status"
    )

    await standing_orders_collection().create_index(
        [("goalId", ASCENDING)],
        unique=True,
        name="uq_goal_open",
        partialFilterExpression={"status": {"$in": ["active", "paused"]}},
    )
    await standing_orders_collection().create_index(
        [("status", ASCENDING), ("nextRunAt", ASCENDING)], name="ix_due"
    )

