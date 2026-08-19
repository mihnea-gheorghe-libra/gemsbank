from motor.motor_asyncio import AsyncIOMotorCollection

from gems.platform.db.client import get_db


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
