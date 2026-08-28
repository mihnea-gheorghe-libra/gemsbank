from backend.helpers.errors import ValidationError
from backend.products.catalogue import CREDIT_PRODUCTS, CreditProduct

_PRODUCTS_BY_ID = {p.id: p for p in CREDIT_PRODUCTS}


def product_for(product_id: str) -> CreditProduct:
    product = _PRODUCTS_BY_ID.get(product_id)
    if product is None:
        raise ValidationError(
            "That is not one of the available credit products.",
            details={"field": "productId", "allowed": sorted(_PRODUCTS_BY_ID)},
        )
    return product


def normalise_amount_minor(raw: int, max_minor: int) -> int:
    if raw <= 0:
        raise ValidationError(
            "That amount must be greater than zero.", details={"field": "amountMinorUnits"}
        )
    if raw > max_minor:
        raise ValidationError(
            "That is more than this product's maximum.",
            details={"field": "amountMinorUnits", "maxMinorUnits": max_minor},
        )
    return raw


def rate_bps_for_term(product: CreditProduct, term_months: int | None) -> int:
    if not product.terms:
        return product.headline_rate_bps
    by_months = {t.months: t.rate_bps for t in product.terms}
    rate_bps = by_months.get(term_months) if term_months is not None else None
    if rate_bps is None:
        raise ValidationError(
            "That is not one of the available terms for this product.",
            details={"field": "termMonths", "allowed": sorted(by_months)},
        )
    return rate_bps


def normalise_purpose(raw: str) -> str:
    candidate = raw.strip()
    if len(candidate) > 140:
        raise ValidationError(
            "Keep the purpose under 140 characters.", details={"field": "purpose"}
        )
    return candidate
