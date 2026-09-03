from datetime import date
from typing import Literal

from backend.helpers.errors import ValidationError

FREQUENCIES = frozenset({"weekly", "monthly"})
MAX_COLLABORATORS = 10
MIN_PERCENT_BP = 100
MAX_PERCENT_BP = 10000


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


def normalise_username_for_invite(raw: str) -> str:
    candidate = raw.strip().lower()
    if not candidate:
        raise ValidationError(
            "Enter the username of the person to invite.",
            details={"field": "username"},
        )
    return candidate


def normalise_share(
    kind: Literal["fixed", "percent"],
    amount_minor: int | None,
    percent_bp: int | None,
) -> tuple[int | None, int | None]:
    if kind == "fixed":
        if amount_minor is None or amount_minor <= 0:
            raise ValidationError(
                "Give a fixed contribution amount greater than zero.",
                details={"field": "amountMinorUnits"},
            )
        return amount_minor, None
    if percent_bp is None or not (MIN_PERCENT_BP <= percent_bp <= MAX_PERCENT_BP):
        raise ValidationError(
            "A percentage share must be between 1% and 100% of the target.",
            details={"field": "percentBp"},
        )
    return None, percent_bp


def normalise_collaborator_count(count: int) -> None:
    if count > MAX_COLLABORATORS:
        raise ValidationError(
            f"A shared goal can have at most {MAX_COLLABORATORS} collaborators.",
            details={"field": "collaborators"},
        )
