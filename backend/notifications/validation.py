from backend.helpers.errors import ValidationError

DEFAULT_LIMIT = 30
MAX_LIMIT = 100


def normalise_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    if limit < 1 or limit > MAX_LIMIT:
        raise ValidationError(
            "limit must be between 1 and 100.", details={"field": "limit"}
        )
    return limit
