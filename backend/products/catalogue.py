from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class Term:
    months: int
    rate_bps: int


@dataclass(slots=True, frozen=True)
class DepositProduct:
    id: str
    kind: str
    default_months: int
    terms: tuple[Term, ...]
    currencies: tuple[str, ...] = ("RON",)


@dataclass(slots=True, frozen=True)
class CreditProduct:
    id: str
    kind: str
    headline_rate_bps: int
    max_minor: int
    currency: str = "RON"
    terms: tuple[Term, ...] = field(default_factory=tuple)


DEPOSIT_PRODUCTS: tuple[DepositProduct, ...] = (
    DepositProduct(
        id="term",
        kind="term",
        default_months=12,
        terms=(
            Term(1, 375),
            Term(3, 480),
            Term(6, 540),
            Term(9, 575),
            Term(12, 610),
            Term(18, 640),
            Term(24, 665),
            Term(36, 690),
        ),
    ),
    DepositProduct(
        id="goal",
        kind="goal",
        default_months=24,
        terms=(Term(12, 260), Term(24, 300), Term(36, 330), Term(60, 360)),
    ),
)


CREDIT_PRODUCTS: tuple[CreditProduct, ...] = (
    CreditProduct(
        id="personal",
        kind="loan",
        headline_rate_bps=890,
        max_minor=15_000_000,
        terms=(
            Term(12, 790),
            Term(24, 830),
            Term(36, 890),
            Term(48, 940),
            Term(60, 990),
        ),
    ),
    CreditProduct(id="line", kind="line", headline_rate_bps=1890, max_minor=2_000_000),
    CreditProduct(
        id="mortgage",
        kind="loan",
        headline_rate_bps=590,
        max_minor=90_000_000,
        terms=(
            Term(120, 520),
            Term(180, 560),
            Term(240, 590),
            Term(300, 635),
            Term(360, 670),
        ),
    ),
)


def format_rate(rate_bps: int) -> str:
    return f"{rate_bps / 100:.2f}".replace(".", ",") + "%"
