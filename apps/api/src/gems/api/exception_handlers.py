import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from gems.platform.errors import DomainError
from gems.platform.observability.correlation import get_correlation_id

logger = logging.getLogger(__name__)


def install(app: FastAPI) -> None:
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
