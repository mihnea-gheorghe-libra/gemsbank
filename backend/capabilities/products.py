from typing import Literal

from pydantic import BaseModel, Field

from backend.capabilities.payments import format_minor
from backend.helpers.context import Actor
from backend.products.catalogue import (
    CREDIT_PRODUCTS,
    DEPOSIT_PRODUCTS,
    format_rate,
)

MAX_TERM_MONTHS = 360


class TermView(BaseModel):
    months: int
    rate_bps: int = Field(alias="rateBps")
    rate_formatted: str = Field(alias="rateFormatted")
    model_config = {"populate_by_name": True}


class DepositProductView(BaseModel):
    id: str
    kind: str
    default_months: int = Field(alias="defaultMonths")
    currencies: list[str]
    terms: list[TermView]
    model_config = {"populate_by_name": True}


class DepositProductsInput(BaseModel):
    pass


class DepositProductsOutput(BaseModel):
    products: list[DepositProductView]
    note: str


class CreditProductView(BaseModel):
    id: str
    kind: str
    headline_rate_bps: int = Field(alias="headlineRateBps")
    headline_rate_formatted: str = Field(alias="headlineRateFormatted")
    max_minor: int = Field(alias="maxMinorUnits")
    max_formatted: str = Field(alias="maxFormatted")
    currency: str
    terms: list[TermView]
    model_config = {"populate_by_name": True}


class CreditProductsInput(BaseModel):
    pass


class CreditProductsOutput(BaseModel):
    products: list[CreditProductView]
    note: str


class RepaymentInput(BaseModel):
    amount_minor: int = Field(
        alias="amountMinorUnits",
        ge=1,
        le=10**12,
        description="How much the customer wants to borrow, in integer minor units.",
    )
    months: int = Field(
        ge=1,
        le=MAX_TERM_MONTHS,
        description="Over how many months they would repay it.",
    )
    rate_bps: int = Field(
        alias="rateBps",
        ge=0,
        le=10_000,
        description=(
            "The annual rate in basis points, taken from a term in "
            "credits.products.list. Never invent one."
        ),
    )
    model_config = {"populate_by_name": True}


class RepaymentOutput(BaseModel):
    status: Literal["ok"]
    monthly_minor: int = Field(alias="monthlyMinorUnits")
    monthly_formatted: str = Field(alias="monthlyFormatted")
    total_repaid_minor: int = Field(alias="totalRepaidMinorUnits")
    total_repaid_formatted: str = Field(alias="totalRepaidFormatted")
    total_interest_minor: int = Field(alias="totalInterestMinorUnits")
    total_interest_formatted: str = Field(alias="totalInterestFormatted")
    caveat: str
    model_config = {"populate_by_name": True}


class MaturityInput(BaseModel):
    amount_minor: int = Field(
        alias="amountMinorUnits",
        ge=1,
        le=10**12,
        description="How much the customer would deposit, in integer minor units.",
    )
    months: int = Field(ge=1, le=MAX_TERM_MONTHS)
    rate_bps: int = Field(
        alias="rateBps",
        ge=0,
        le=10_000,
        description=(
            "The annual rate in basis points, taken from a term in "
            "deposits.products.list. Never invent one."
        ),
    )
    currency: str = Field(default="RON", min_length=3, max_length=3)
    model_config = {"populate_by_name": True}


class MaturityOutput(BaseModel):
    status: Literal["ok"]
    interest_minor: int = Field(alias="interestMinorUnits")
    interest_formatted: str = Field(alias="interestFormatted")
    total_minor: int = Field(alias="totalMinorUnits")
    total_formatted: str = Field(alias="totalFormatted")
    caveat: str
    model_config = {"populate_by_name": True}


_DEPOSIT_NOTE = (
    "These are demo product terms. Opening a deposit is not wired to the ledger in this "
    "system: nothing you say here opens, funds or reserves anything."
)

_CREDIT_NOTE = (
    "These are demo product terms, not an offer and not a credit decision. Nobody is "
    "assessed, approved or refused here, and no application is filed by this conversation."
)

_SIMPLE_INTEREST_CAVEAT = (
    "Simple interest, straight-line, no compounding, no fees and no taxes. It is an "
    "illustration of the demo product terms, not a quote."
)


def _terms(product) -> list[TermView]:
    return [
        TermView(months=t.months, rateBps=t.rate_bps, rateFormatted=format_rate(t.rate_bps))
        for t in product.terms
    ]


async def resolve_deposit_products(_actor: Actor, payload: BaseModel) -> BaseModel:
    assert isinstance(payload, DepositProductsInput)
    return DepositProductsOutput(
        products=[
            DepositProductView(
                id=p.id,
                kind=p.kind,
                defaultMonths=p.default_months,
                currencies=list(p.currencies),
                terms=_terms(p),
            )
            for p in DEPOSIT_PRODUCTS
        ],
        note=_DEPOSIT_NOTE,
    )


async def resolve_credit_products(_actor: Actor, payload: BaseModel) -> BaseModel:
    assert isinstance(payload, CreditProductsInput)
    return CreditProductsOutput(
        products=[
            CreditProductView(
                id=p.id,
                kind=p.kind,
                headlineRateBps=p.headline_rate_bps,
                headlineRateFormatted=format_rate(p.headline_rate_bps),
                maxMinorUnits=p.max_minor,
                maxFormatted=format_minor(p.max_minor, p.currency),
                currency=p.currency,
                terms=_terms(p),
            )
            for p in CREDIT_PRODUCTS
        ],
        note=_CREDIT_NOTE,
    )


async def resolve_repayment_estimate(_actor: Actor, payload: BaseModel) -> BaseModel:
    assert isinstance(payload, RepaymentInput)
    years = payload.months / 12
    interest = round(payload.amount_minor * (payload.rate_bps / 10_000) * years)
    total = payload.amount_minor + interest
    monthly = round(total / payload.months)
    return RepaymentOutput(
        status="ok",
        monthlyMinorUnits=monthly,
        monthlyFormatted=format_minor(monthly, "RON"),
        totalRepaidMinorUnits=total,
        totalRepaidFormatted=format_minor(total, "RON"),
        totalInterestMinorUnits=interest,
        totalInterestFormatted=format_minor(interest, "RON"),
        caveat=_SIMPLE_INTEREST_CAVEAT,
    )


async def resolve_maturity_estimate(_actor: Actor, payload: BaseModel) -> BaseModel:
    assert isinstance(payload, MaturityInput)
    years = payload.months / 12
    interest = round(payload.amount_minor * (payload.rate_bps / 10_000) * years)
    total = payload.amount_minor + interest
    currency = payload.currency.upper()
    return MaturityOutput(
        status="ok",
        interestMinorUnits=interest,
        interestFormatted=format_minor(interest, currency),
        totalMinorUnits=total,
        totalFormatted=format_minor(total, currency),
        caveat=_SIMPLE_INTEREST_CAVEAT,
    )
