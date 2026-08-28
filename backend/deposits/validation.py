from backend.helpers.errors import ValidationError
from backend.products.catalogue import DEPOSIT_PRODUCTS

_TERM_PRODUCT = next(p for p in DEPOSIT_PRODUCTS if p.id == "term")
_TERMS_BY_MONTHS = {t.months: t.rate_bps for t in _TERM_PRODUCT.terms}


def normalise_name(raw: str) -> str:
    candidate = raw.strip()
    if not (1 <= len(candidate) <= 80):
        raise ValidationError(
            "Give the deposit a short name, up to 80 characters.", details={"field": "name"}
        )
    return candidate


def rate_bps_for_term(term_months: int) -> int:
    rate_bps = _TERMS_BY_MONTHS.get(term_months)
    if rate_bps is None:
        raise ValidationError(
            "That is not one of the available deposit terms.",
            details={"field": "termMonths", "allowed": sorted(_TERMS_BY_MONTHS)},
        )
    return rate_bps


def normalise_movement_minor(raw: int, field: str) -> int:
    if raw <= 0:
        raise ValidationError(
            "That amount must be greater than zero.", details={"field": field}
        )
    return raw
