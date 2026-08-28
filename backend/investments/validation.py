from datetime import date, datetime, timezone
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

from backend.helpers.errors import ValidationError

MINOR_SCALE = Decimal(100)
RATE_SCALE = Decimal(1_000_000)
QUANTITY_SCALE = Decimal(1_000_000)

_SUPPORTED_RANGES = frozenset({"1mo", "3mo", "6mo", "1y", "2y", "5y"})


def _to_decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValidationError("Upstream returned no usable number.", details={"field": field})
    try:
        candidate = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError(
            "Upstream returned a number we cannot read.", details={"field": field}
        ) from exc
    if not candidate.is_finite():
        raise ValidationError("Upstream returned a non-finite number.", details={"field": field})
    return candidate


def to_minor_units(value: object, field: str) -> int:
    candidate = _to_decimal(value, field)
    if candidate < 0:
        raise ValidationError("A price cannot be negative.", details={"field": field})
    return int((candidate * MINOR_SCALE).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def to_rate_micro(value: object, field: str) -> int:
    candidate = _to_decimal(value, field)
    if candidate <= 0:
        raise ValidationError("An exchange rate must be positive.", details={"field": field})
    return int((candidate * RATE_SCALE).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def convert_minor(amount_minor: int, rate_micro: int) -> int:
    converted = (Decimal(amount_minor) * Decimal(rate_micro)) / RATE_SCALE
    return int(converted.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def normalise_range(value: str | None) -> str:
    candidate = (value or "6mo").strip().lower()
    if candidate not in _SUPPORTED_RANGES:
        raise ValidationError(
            "That history range is not supported.",
            details={"field": "range", "supported": sorted(_SUPPORTED_RANGES)},
        )
    return candidate


def to_quantity_micro(amount_minor: int, unit_price_minor: int) -> int:
    if unit_price_minor <= 0:
        raise ValidationError("This instrument has no usable price right now.")
    quantity = (Decimal(amount_minor) * QUANTITY_SCALE) / Decimal(unit_price_minor)
    result = int(quantity.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
    if result <= 0:
        raise ValidationError(
            "That amount is too small to trade any units.", details={"field": "amountMinor"}
        )
    return result


def holding_value_minor(quantity_micro: int, unit_price_minor: int) -> int:
    value = (Decimal(quantity_micro) * Decimal(unit_price_minor)) / QUANTITY_SCALE
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def epoch_to_date(value: object, field: str) -> date:
    candidate = _to_decimal(value, field)
    return datetime.fromtimestamp(int(candidate), tz=timezone.utc).date()
