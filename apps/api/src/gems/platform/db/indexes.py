from pymongo import ASCENDING, DESCENDING

from gems.platform.db.collections import (
    audit_log_collection,
    idempotency_collection,
    kyc_cases_collection,
    outbox_collection,
    users_collection,
)


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
    await audit_log_collection().create_index(
        [("correlationId", ASCENDING)], name="ix_correlation"
    )

    await outbox_collection().create_index(
        [("dispatchedAt", ASCENDING), ("occurredAt", ASCENDING)], name="ix_undispatched"
    )
