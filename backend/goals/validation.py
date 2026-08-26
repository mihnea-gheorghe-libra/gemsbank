from datetime import date

from backend.helpers.errors import ValidationError


def normalise_name(raw: str) -> str:
    candidate = raw.strip()
    if not (1 <= len(candidate) <= 80):
        raise ValidationError(
            "Give the goal a short name, up to 80 characters.", details={"field": "name"}
        )
    return candidate


def normalise_target_minor(raw: int) -> int:
    if raw <= 0:
        raise ValidationError(
            "The target amount must be greater than zero.", details={"field": "targetMinorUnits"}
        )
    return raw


def normalise_target_date(raw: date, today: date) -> date:
    if raw <= today:
        raise ValidationError(
            "The target date must be in the future.", details={"field": "targetDate"}
        )
    return raw
