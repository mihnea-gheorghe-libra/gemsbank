from typing import Any


class DomainError(Exception):
    code = "domain_error"
    http_status = 400

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_payload(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class ValidationError(DomainError):
    code = "validation_error"
    http_status = 422


class NotFoundError(DomainError):
    code = "not_found"
    http_status = 404


class ConflictError(DomainError):
    code = "conflict"
    http_status = 409


class IllegalTransitionError(ConflictError):
    code = "illegal_transition"


class RateLimitedError(DomainError):
    code = "rate_limited"
    http_status = 429


class AuthenticationError(DomainError):
    code = "authentication_failed"
    http_status = 401


class DeliveryError(DomainError):
    code = "delivery_failed"
    http_status = 502


class EligibilityError(DomainError):
    code = "not_eligible"
    http_status = 422
