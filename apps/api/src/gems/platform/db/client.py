import motor.motor_asyncio
from gems.config import settings

_client: motor.motor_asyncio.AsyncIOMotorClient | None = None

def get_client() -> motor.motor_asyncio.AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = motor.motor_asyncio.AsyncIOMotorClient(settings.mongo_uri)
    return _client

def get_db():
    return get_client()[settings.mongo_db_name]