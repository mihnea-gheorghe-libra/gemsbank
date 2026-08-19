from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from gems.platform.observability.correlation import CORRELATION_HEADER, set_correlation_id


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def correlation_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        correlation_id = set_correlation_id(request.headers.get(CORRELATION_HEADER))
        response = await call_next(request)
        response.headers[CORRELATION_HEADER] = correlation_id
        return response
