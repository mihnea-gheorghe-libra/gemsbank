from datetime import date

from backend.helpers.errors import ValidationError

FREQUENCIES = frozenset({"weekly", "monthly"})


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


def normalise_movement_minor(raw: int, field: str) -> int:
    if raw <= 0:
        raise ValidationError(
            "That amount must be greater than zero.", details={"field": field}
        )
    return raw


def normalise_frequency(raw: str) -> str:
    candidate = raw.strip().lower()
    if candidate not in FREQUENCIES:
        raise ValidationError(
            "Frequency must be 'weekly' or 'monthly'.", details={"field": "frequency"}
        )
    return candidate
