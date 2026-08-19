import json
import logging
import sys
from contextvars import ContextVar

from gems.platform.ids import new_id

CORRELATION_HEADER = "X-Correlation-Id"

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def set_correlation_id(value: str | None) -> str:
    resolved = value or new_id()
    _correlation_id.set(resolved)
    return resolved


def get_correlation_id() -> str:
    current = _correlation_id.get()
    if not current:
        return set_correlation_id(None)
    return current


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }
        extra = getattr(record, "context", None)
        if isinstance(extra, dict):
            payload |= extra
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def log_event(logger: logging.Logger, message: str, **context: object) -> None:
    logger.info(message, extra={"context": context})
