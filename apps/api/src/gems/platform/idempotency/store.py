from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClientSession
from pymongo.errors import DuplicateKeyError

from gems.platform.db.collections import idempotency_collection
from gems.platform.errors import ConflictError


async def find_stored_response(scope: str, key: str) -> dict[str, Any] | None:
    document = await idempotency_collection().find_one({"scope": scope, "key": key})
    if document is None:
        return None
    return document.get("response")


async def store_response(
    scope: str,
    key: str,
    response: dict[str, Any],
    session: AsyncIOMotorClientSession | None = None,
) -> None:
    try:
        await idempotency_collection().insert_one(
            {
                "scope": scope,
                "key": key,
                "response": response,
                "createdAt": datetime.now(timezone.utc),
            },
            session=session,
        )
    except DuplicateKeyError as exc:
        raise ConflictError(
            "This idempotency key was already used for a different request.",
            details={"scope": scope},
        ) from exc
