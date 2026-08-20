from backend.helpers.errors import ValidationError

MIN_LIMIT_MINOR = 0
MAX_LIMIT_MINOR = 50_000_00  # RON 50 000,00 — a sane demo ceiling, not a real product limit


def validate_limit_minor(raw: int, field: str) -> int:
    if raw < MIN_LIMIT_MINOR or raw > MAX_LIMIT_MINOR:
        raise ValidationError(
            f"The limit must be between {MIN_LIMIT_MINOR} and {MAX_LIMIT_MINOR} minor units.",
            details={"field": field},
        )
    return raw
