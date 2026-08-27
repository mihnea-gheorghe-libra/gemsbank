from typing import Literal

from pydantic import BaseModel, Field

from backend.capabilities.payments import format_minor
from backend.helpers.context import Actor
from backend.investments.service import InvestmentsService, get_investments_service

RANGES = ("1mo", "3mo", "6mo", "1y")

_MARKET_NOTE = (
    "Prices are real and fetched live from public providers, converted to RON. Buying and "
    "selling is not wired to the ledger in this system: nothing you say here trades, orders "
    "or reserves anything."
)


class MarketInput(BaseModel):
    range: Literal["1mo", "3mo", "6mo", "1y"] = Field(
        default="6mo",
        description="How far back the price history should reach.",
    )
    instrument_id: str | None = Field(
        default=None,
        alias="instrumentId",
        max_length=32,
        description=(
            "Optional. Restrict to one instrument by its id (h-msci, h-tlv, h-btc). "
            "Leave empty for all of them."
        ),
    )
    model_config = {"populate_by_name": True}


class HistoryPointView(BaseModel):
    on: str
    unit_price_formatted: str = Field(alias="unitPriceFormatted")
    model_config = {"populate_by_name": True}


class QuoteView(BaseModel):
    id: str
    name: str
    symbol: str
    asset_class: str = Field(alias="assetClass")
    currency: str
    unit_price_minor: int = Field(alias="unitPriceMinorUnits")
    unit_price_formatted: str = Field(alias="unitPriceFormatted")
    change_bps: int = Field(alias="changeBps")
    change_formatted: str = Field(alias="changeFormatted")
    as_of: str = Field(alias="asOf")
    period_low_formatted: str | None = Field(default=None, alias="periodLowFormatted")
    period_high_formatted: str | None = Field(default=None, alias="periodHighFormatted")
    period_change_formatted: str | None = Field(default=None, alias="periodChangeFormatted")
    history_points: int = Field(default=0, alias="historyPoints")
    model_config = {"populate_by_name": True}


class MarketOutput(BaseModel):
    status: Literal["ok", "no_match"]
    live: bool
    refreshed_at: str | None = Field(default=None, alias="refreshedAt")
    currency: str = "RON"
    range: str = "6mo"
    quotes: list[QuoteView] = Field(default_factory=list)
    known_instrument_ids: list[str] = Field(default_factory=list, alias="knownInstrumentIds")
    staleness_note: str | None = Field(default=None, alias="stalenessNote")
    note: str = _MARKET_NOTE
    model_config = {"populate_by_name": True}


def _change_formatted(change_bps: int) -> str:
    sign = "+" if change_bps > 0 else ""
    return f"{sign}{change_bps / 100:.2f}".replace(".", ",") + "%"


def _quote_view(raw: dict, currency: str) -> QuoteView:
    history = raw.get("history") or []
    prices = [point["unitPriceMinor"] for point in history if "unitPriceMinor" in point]
    low = min(prices) if prices else None
    high = max(prices) if prices else None
    period_change = None
    if len(prices) >= 2 and prices[0]:
        period_change = _change_formatted(round((prices[-1] - prices[0]) / prices[0] * 10_000))

    return QuoteView(
        id=raw["id"],
        name=raw["name"],
        symbol=raw["symbol"],
        assetClass=raw["assetClass"],
        currency=currency,
        unitPriceMinorUnits=raw["unitPriceMinor"],
        unitPriceFormatted=format_minor(raw["unitPriceMinor"], currency),
        changeBps=raw["changeBps"],
        changeFormatted=_change_formatted(raw["changeBps"]),
        asOf=raw["asOf"],
        periodLowFormatted=format_minor(low, currency) if low is not None else None,
        periodHighFormatted=format_minor(high, currency) if high is not None else None,
        periodChangeFormatted=period_change,
        historyPoints=len(prices),
    )


async def resolve_market(
    _actor: Actor,
    payload: BaseModel,
    investments: InvestmentsService | None = None,
) -> BaseModel:
    assert isinstance(payload, MarketInput)
    service = investments or get_investments_service()
    snapshot = await service.market(payload.range)

    currency = snapshot.get("currency", "RON")
    quotes = snapshot.get("quotes") or []
    known = [row["id"] for row in quotes]

    if payload.instrument_id:
        quotes = [row for row in quotes if row["id"] == payload.instrument_id]
        if not quotes:
            return MarketOutput(
                status="no_match",
                live=bool(snapshot.get("live")),
                refreshedAt=snapshot.get("refreshedAt"),
                currency=currency,
                range=payload.range,
                knownInstrumentIds=known,
            )

    live = bool(snapshot.get("live"))
    return MarketOutput(
        status="ok",
        live=live,
        refreshedAt=snapshot.get("refreshedAt"),
        currency=currency,
        range=payload.range,
        quotes=[_quote_view(row, currency) for row in quotes],
        knownInstrumentIds=known,
        stalenessNote=(
            None
            if live
            else (
                "A provider is unreachable, so these are the last prices GEMS successfully "
                "fetched. Say so, and give the timestamp, before quoting any of them."
            )
        ),
    )
