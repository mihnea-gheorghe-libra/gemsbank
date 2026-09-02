import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.accounts.service import get_accounts_service
from backend.admin.service import get_admin_service
from backend.auth.service import get_auth_service
from backend.capabilities.service import get_capabilities_service
from backend.cards.service import get_cards_service
from backend.config import settings
from backend.database.mongo import close_client, ensure_indexes
from backend.escalations.service import get_escalations_service
from backend.exchange.service import get_exchange_service
from backend.goals.service import get_goals_service
from backend.helpers.context import (
    CORRELATION_HEADER,
    configure_logging,
    get_correlation_id,
    set_correlation_id,
)
from backend.helpers.errors import DomainError
from backend.investments.service import (
    close_investments_clients,
    get_investments_service,
)
from backend.onboarding.service import get_onboarding_service
from backend.payments.service import get_payments_service
from backend.server.routes import api_router

logger = logging.getLogger(__name__)


async def _standing_orders_loop() -> None:
    goals = get_goals_service()
    while True:
        try:
            executed = await goals.run_due_standing_orders()
            if executed:
                logger.info("standing_orders_run", extra={"context": {"executed": executed}})
        except Exception:
            logger.exception("standing_orders_loop_failed")
        await asyncio.sleep(settings.standing_orders_poll_seconds)


async def _index_reassert_loop() -> None:
    while True:
        await asyncio.sleep(settings.index_reassert_seconds)
        try:
            await ensure_indexes()
        except Exception:
            logger.exception("index_reassert_loop_failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    get_accounts_service()
    get_payments_service()
    get_onboarding_service()
    get_auth_service()
    get_cards_service()
    get_investments_service()
    get_capabilities_service()
    get_goals_service()
    get_exchange_service()
    get_escalations_service()
    get_admin_service()
    await ensure_indexes()
    standing_orders_task = asyncio.create_task(_standing_orders_loop())
    index_reassert_task = asyncio.create_task(_index_reassert_loop())
    yield
    index_reassert_task.cancel()
    standing_orders_task.cancel()
    await close_investments_clients()
    await close_client()


app = FastAPI(
    title="gems-bank API",
    version="0.1.0",
    description="Demo system. No licence, no real funds, no real card data.",
    lifespan=lifespan,
)


@app.middleware("http")
async def correlation_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    correlation_id = set_correlation_id(request.headers.get(CORRELATION_HEADER))
    response = await call_next(request)
    response.headers[CORRELATION_HEADER] = correlation_id
    return response


@app.exception_handler(DomainError)
async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
    payload = exc.to_payload()
    payload["error"]["correlationId"] = get_correlation_id()
    return JSONResponse(status_code=exc.http_status, content=payload)


@app.exception_handler(RequestValidationError)
async def handle_request_validation(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "The request body is not valid.",
                "details": {"fields": exc.errors()},
                "correlationId": get_correlation_id(),
            }
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", extra={"context": {"path": request.url.path}})
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "Something went wrong on our side.",
                "details": {},
                "correlationId": get_correlation_id(),
            }
        },
    )


app.include_router(api_router)


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/app/")


class UncachedStaticFiles(StaticFiles):
    def file_response(self, *args: Any, **kwargs: Any) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-store"
        return response


_web_dir = Path(settings.web_dir)
if _web_dir.is_dir():
    app.mount("/app", UncachedStaticFiles(directory=_web_dir, html=True), name="web")
