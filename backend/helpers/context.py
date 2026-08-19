import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Literal

from pydantic import BaseModel, Field

CORRELATION_HEADER = "X-Correlation-Id"

ActorKind = Literal["user", "system", "agent"]

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def uuid7() -> uuid.UUID:
    unix_ms = int(time.time() * 1000)
    rand = os.urandom(10)

    value = bytearray(16)
    value[0:6] = unix_ms.to_bytes(6, "big")
    value[6:16] = rand
    value[6] = (value[6] & 0x0F) | 0x70
    value[8] = (value[8] & 0x3F) | 0x80
    return uuid.UUID(bytes=bytes(value))


def new_id() -> str:
    return str(uuid7())


class Actor(BaseModel):
    kind: ActorKind
    id: str
    on_behalf_of: str | None = None
    mandate_id: str | None = None

    @classmethod
    def public_onboarding(cls) -> "Actor":
        return cls(kind="system", id="public-onboarding")

    @classmethod
    def user(cls, user_id: str) -> "Actor":
        return cls(kind="user", id=user_id)

    def label(self) -> str:
        return f"{self.kind}:{self.id}"


class ActorContext(BaseModel):
    actor: Actor
    correlation_id: str
    ip: str | None = None
    user_agent: str | None = Field(default=None)


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
