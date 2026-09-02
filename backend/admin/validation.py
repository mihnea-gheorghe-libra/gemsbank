from backend.helpers.errors import ValidationError

REASON_MIN_LENGTH = 5
REASON_MAX_LENGTH = 280
SEARCH_MAX_LENGTH = 64
MAX_PAGE_SIZE = 100

INCOME_LOOKBACK_MONTHS = 3
INCOME_LOOKBACK_DAYS = 92
INCOME_SAMPLE_LIMIT = 200

DECIDABLE_STATUSES = ("review", "approved", "rejected", "withdrawn")


def normalise_reason(raw: str) -> str:
    candidate = " ".join(raw.split())
    if len(candidate) < REASON_MIN_LENGTH:
        raise ValidationError(
            f"Give a reason of at least {REASON_MIN_LENGTH} characters.",
            details={"field": "reason", "minLength": REASON_MIN_LENGTH},
        )
    if len(candidate) > REASON_MAX_LENGTH:
        raise ValidationError(
            f"Keep the reason under {REASON_MAX_LENGTH} characters.",
            details={"field": "reason", "maxLength": REASON_MAX_LENGTH},
        )
    return candidate


def normalise_search(raw: str | None) -> str | None:
    if raw is None:
        return None
    candidate = raw.strip()
    if not candidate:
        return None
    if len(candidate) > SEARCH_MAX_LENGTH:
        raise ValidationError(
            f"Keep the search under {SEARCH_MAX_LENGTH} characters.",
            details={"field": "search", "maxLength": SEARCH_MAX_LENGTH},
        )
    return candidate


def normalise_page_size(raw: int | None, fallback: int) -> int:
    if raw is None:
        return fallback
    if raw < 1:
        raise ValidationError(
            "A page must hold at least one row.", details={"field": "limit"}
        )
    return min(raw, MAX_PAGE_SIZE)


def normalise_application_status(raw: str | None) -> str | None:
    if raw is None or not raw.strip():
        return None
    candidate = raw.strip().lower()
    if candidate not in DECIDABLE_STATUSES:
        raise ValidationError(
            "That is not one of the application statuses.",
            details={"field": "status", "allowed": list(DECIDABLE_STATUSES)},
        )
    return candidate
