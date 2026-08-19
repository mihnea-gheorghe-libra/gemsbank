from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from gems.config import settings

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
