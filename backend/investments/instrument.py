from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class AssetClass(str, Enum):
    EQUITY = "equity"
    FUND = "fund"
    CRYPTO = "crypto"


class Instrument(BaseModel):
    id: str
    symbol: str
    name: str
    asset_class: AssetClass
    unit_key: str
    quote_currency: str
    fallback_unit_price_minor: int


class HistoryPoint(BaseModel):
    on: date
    unit_price_minor: int

    def public_view(self) -> dict[str, Any]:
        return {"on": self.on.isoformat(), "unitPriceMinor": self.unit_price_minor}


class Quote(BaseModel):
    instrument_id: str
    symbol: str
    name: str
    asset_class: AssetClass
    unit_key: str
    quote_currency: str
    quote_unit_price_minor: int
    currency: str
    unit_price_minor: int
    previous_close_minor: int | None
    as_of: datetime
    live: bool
    history: list[HistoryPoint]

    def change_bps(self) -> int | None:
        if self.previous_close_minor is None or self.previous_close_minor == 0:
            return None
        delta = self.unit_price_minor - self.previous_close_minor
        return round(delta * 10_000 / self.previous_close_minor)

    def public_view(self) -> dict[str, Any]:
        return {
            "id": self.instrument_id,
            "symbol": self.symbol,
            "name": self.name,
            "assetClass": self.asset_class.value,
            "unitKey": self.unit_key,
            "quoteCurrency": self.quote_currency,
            "quoteUnitPriceMinor": self.quote_unit_price_minor,
            "currency": self.currency,
            "unitPriceMinor": self.unit_price_minor,
            "previousCloseMinor": self.previous_close_minor,
            "changeBps": self.change_bps(),
            "asOf": self.as_of.isoformat(),
            "live": self.live,
            "history": [point.public_view() for point in self.history],
        }


class ExchangeRate(BaseModel):
    base: str
    quote: str
    rate_micro: int
    as_of: date
    live: bool

    def public_view(self) -> dict[str, Any]:
        return {
            "base": self.base,
            "quote": self.quote,
            "rateMicro": self.rate_micro,
            "asOf": self.as_of.isoformat(),
            "live": self.live,
        }


class MarketSnapshot(BaseModel):
    currency: str
    quotes: list[Quote]
    rates: list[ExchangeRate]
    refreshed_at: datetime
    live: bool

    def public_view(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "quotes": [quote.public_view() for quote in self.quotes],
            "rates": [rate.public_view() for rate in self.rates],
            "refreshedAt": self.refreshed_at.isoformat(),
            "live": self.live,
        }
