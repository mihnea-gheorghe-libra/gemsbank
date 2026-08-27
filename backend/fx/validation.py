from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

RATE_SCALE = Decimal(1_000_000)
BASE_CURRENCY = "RON"
RATE_DECIMALS = 4


def to_rate_micro(value: object, multiplier: int = 1) -> int:
    if isinstance(multiplier, bool) or not isinstance(multiplier, int) or multiplier <= 0:
        raise ValueError(f"a BNR multiplier is a positive integer, got {multiplier!r}")
    if isinstance(value, bool) or value is None:
        raise ValueError(f"a BNR rate must be a number, got {value!r}")
    try:
        candidate = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"unreadable BNR rate {value!r}") from error
    if not candidate.is_finite() or candidate <= 0:
        raise ValueError(f"a BNR rate must be positive, got {value!r}")
    scaled = candidate * RATE_SCALE / Decimal(multiplier)
    return int(scaled.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def rate_text(rate_micro: int, decimal_separator: str = ".") -> str:
    quantum = Decimal(1).scaleb(-RATE_DECIMALS)
    value = (Decimal(rate_micro) / RATE_SCALE).quantize(quantum, rounding=ROUND_HALF_EVEN)
    return f"{value:f}".replace(".", decimal_separator)


def percent_text(value: float, decimal_separator: str = ".") -> str:
    return f"{abs(value):.1f}".replace(".", decimal_separator)


def percent_change(current_micro: int, baseline_micro: int) -> float:
    if baseline_micro <= 0:
        return 0.0
    return (current_micro - baseline_micro) / baseline_micro * 100.0


def convert_minor(amount_minor: int, rate_micro: int) -> int:
    converted = Decimal(amount_minor) * Decimal(rate_micro) / RATE_SCALE
    return int(converted.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def normalise_feed_currency(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    candidate = raw.strip().upper()
    if len(candidate) != 3 or not candidate.isalpha():
        return None
    return candidate
