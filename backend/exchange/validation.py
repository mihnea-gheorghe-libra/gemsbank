from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

from backend.helpers.errors import ValidationError
from backend.ledger.validation import SUPPORTED_CURRENCIES, normalise_currency

RATE_SCALE = Decimal(1_000_000)


def to_rate_micro(value: object, field: str) -> int:
    if isinstance(value, bool) or value is None:
        raise ValidationError("Upstream returned no usable rate.", details={"field": field})
    try:
        candidate = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError(
            "Upstream returned a rate we cannot read.", details={"field": field}
        ) from exc
    if not candidate.is_finite() or candidate <= 0:
        raise ValidationError("An exchange rate must be a positive number.", details={"field": field})
    return int((candidate * RATE_SCALE).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def convert_minor(amount_minor: int, rate_micro: int) -> int:
    converted = (Decimal(amount_minor) * Decimal(rate_micro)) / RATE_SCALE
    return int(converted.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def normalise_pair(source_currency: str, target_currency: str) -> tuple[str, str]:
    source = normalise_currency(source_currency)
    target = normalise_currency(target_currency)
    if source == target:
        raise ValidationError(
            "Pick two different currencies to convert between.",
            details={"field": "targetCurrency"},
        )
    return source, target


def supported_currencies() -> list[str]:
    return sorted(SUPPORTED_CURRENCIES)
