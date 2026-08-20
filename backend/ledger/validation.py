import re

from backend.helpers.errors import ValidationError

CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
SUPPORTED_CURRENCIES = frozenset({"RON", "EUR"})
MAX_MINOR_UNITS = 10**12


def normalise_currency(raw: str) -> str:
    candidate = raw.strip().upper()
    if not CURRENCY_PATTERN.match(candidate):
        raise ValidationError(
            "A currency is a three-letter ISO 4217 code.", details={"field": "currency"}
        )
    if candidate not in SUPPORTED_CURRENCIES:
        raise ValidationError(
            f"GEMS does not hold {candidate} accounts.",
            details={"field": "currency", "supported": sorted(SUPPORTED_CURRENCIES)},
        )
    return candidate


def validate_minor_units(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(
            "An amount is an integer number of minor units.", details={"field": "amount"}
        )
    if value <= 0:
        raise ValidationError("An amount must be greater than zero.", details={"field": "amount"})
    if value > MAX_MINOR_UNITS:
        raise ValidationError(
            "That amount is larger than this demo will carry.", details={"field": "amount"}
        )
    return value
