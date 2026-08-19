from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from gems.api import exception_handlers, middleware
from gems.api.router import api_router
from gems.config import settings
from gems.modules.identity.composition import get_onboarding_service
from gems.platform.db.client import close_client
from gems.platform.db.indexes import ensure_indexes
from gems.platform.observability.correlation import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    get_onboarding_service()
    await ensure_indexes()
    yield
    await close_client()


app = FastAPI(
    title="gems-bank API",
    version="0.1.0",
    description="Demo system. No licence, no real funds, no real card data.",
    lifespan=lifespan,
)

middleware.install(app)
exception_handlers.install(app)
app.include_router(api_router)


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/app/")


_web_dir = Path(settings.web_dir)
if _web_dir.is_dir():
    app.mount("/app", StaticFiles(directory=_web_dir, html=True), name="web")
