from typing import Any

from fastapi import APIRouter

from gems.modules.identity.api.routes import router as onboarding_router
from gems.platform.commandbus.bus import bus
from gems.platform.db.client import get_db

api_router = APIRouter()


@api_router.get("/health", tags=["platform"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@api_router.get("/system/status", tags=["platform"])
async def system_status() -> dict[str, Any]:
    result = await get_db().command("ping")
    return {
        "status": "operational" if result.get("ok") == 1.0 else "degraded",
        "demo": True,
        "notice": "Demo system. No licence, no real funds, no real card data.",
        "incidents": [],
    }


@api_router.get("/capabilities", tags=["platform"])
async def capabilities() -> dict[str, Any]:
    return {"commands": bus.registered_commands()}


api_router.include_router(onboarding_router)
