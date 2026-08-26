from datetime import date, datetime, timezone
from typing import Any

import httpx
from pydantic import BaseModel

from backend.helpers.errors import DeliveryError
from backend.investments.instrument import AssetClass, HistoryPoint, Instrument
from backend.investments.validation import epoch_to_date, to_minor_units, to_rate_micro

CATALOGUE: tuple[Instrument, ...] = (
    Instrument(
        id="h-msci",
        symbol="URTH",
        name="MSCI World ETF",
        asset_class=AssetClass.FUND,
        unit_key="units",
        quote_currency="USD",
        fallback_unit_price_minor=18_000,
    ),
    Instrument(
        id="h-tlv",
        symbol="TLV.RO",
        name="TLV — Banca Transilvania",
        asset_class=AssetClass.EQUITY,
        unit_key="shares",
        quote_currency="RON",
        fallback_unit_price_minor=3_150,
    ),
    Instrument(
        id="h-btc",
        symbol="BTC-USD",
        name="BTC",
        asset_class=AssetClass.CRYPTO,
        unit_key="coins",
        quote_currency="USD",
        fallback_unit_price_minor=9_500_000,
    ),
    Instrument(
        id="h-spy",
        symbol="SPY",
        name="S&P 500 ETF",
        asset_class=AssetClass.FUND,
        unit_key="units",
        quote_currency="USD",
        fallback_unit_price_minor=56_000,
    ),
    Instrument(
        id="h-aapl",
        symbol="AAPL",
        name="Apple",
        asset_class=AssetClass.EQUITY,
        unit_key="shares",
        quote_currency="USD",
        fallback_unit_price_minor=23_000,
    ),
    Instrument(
        id="h-snp",
        symbol="SNP.RO",
        name="OMV Petrom",
        asset_class=AssetClass.EQUITY,
        unit_key="shares",
        quote_currency="RON",
        fallback_unit_price_minor=50,
    ),
    Instrument(
        id="h-eth",
        symbol="ETH-USD",
        name="Ethereum",
        asset_class=AssetClass.CRYPTO,
        unit_key="coins",
        quote_currency="USD",
        fallback_unit_price_minor=380_000,
    ),
    Instrument(
        id="h-msft",
        symbol="MSFT",
        name="Microsoft",
        asset_class=AssetClass.EQUITY,
        unit_key="shares",
        quote_currency="USD",
        fallback_unit_price_minor=47_000,
    ),
    Instrument(
        id="h-amzn",
        symbol="AMZN",
        name="Amazon",
        asset_class=AssetClass.EQUITY,
        unit_key="shares",
        quote_currency="USD",
        fallback_unit_price_minor=22_000,
    ),
    Instrument(
        id="h-googl",
        symbol="GOOGL",
        name="Alphabet",
        asset_class=AssetClass.EQUITY,
        unit_key="shares",
        quote_currency="USD",
        fallback_unit_price_minor=19_000,
    ),
    Instrument(
        id="h-nvda",
        symbol="NVDA",
        name="Nvidia",
        asset_class=AssetClass.EQUITY,
        unit_key="shares",
        quote_currency="USD",
        fallback_unit_price_minor=13_500,
    ),
    Instrument(
        id="h-meta",
        symbol="META",
        name="Meta",
        asset_class=AssetClass.EQUITY,
        unit_key="shares",
        quote_currency="USD",
        fallback_unit_price_minor=62_000,
    ),
    Instrument(
        id="h-tsla",
        symbol="TSLA",
        name="Tesla",
        asset_class=AssetClass.EQUITY,
        unit_key="shares",
        quote_currency="USD",
        fallback_unit_price_minor=26_000,
    ),
    Instrument(
        id="h-gld",
        symbol="GLD",
        name="Gold",
        asset_class=AssetClass.FUND,
        unit_key="units",
        quote_currency="USD",
        fallback_unit_price_minor=25_000,
    ),
    Instrument(
        id="h-slv",
        symbol="SLV",
        name="Silver",
        asset_class=AssetClass.FUND,
        unit_key="units",
        quote_currency="USD",
        fallback_unit_price_minor=2_900,
    ),
    Instrument(
        id="h-pplt",
        symbol="PPLT",
        name="Platinum",
        asset_class=AssetClass.FUND,
        unit_key="units",
        quote_currency="USD",
        fallback_unit_price_minor=9_700,
    ),
)

FALLBACK_RATES: dict[str, int] = {"USD": 4_550_000, "EUR": 4_975_000}

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class ChartResult(BaseModel):
    symbol: str
    currency: str
    unit_price_minor: int
    previous_close_minor: int | None
    as_of: datetime
    history: list[HistoryPoint]


class RateResult(BaseModel):
    base: str
    quote: str
    rate_micro: int
    as_of: date


class HttpTransport:
    def __init__(self, timeout_seconds: float) -> None:
        self._timeout = timeout_seconds
        self._client: httpx.AsyncClient | None = None

    def _ensure(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
                headers={"User-Agent": _BROWSER_UA, "Accept": "application/json"},
                follow_redirects=True,
            )
        return self._client

    async def get_json(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = await self._ensure().get(url, params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise DeliveryError(
                "The market data provider did not answer.",
                details={"url": url},
            ) from exc
        if not isinstance(payload, dict):
            raise DeliveryError(
                "The market data provider answered in an unexpected shape.",
                details={"url": url},
            )
        return payload

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


class YahooChartClient:
    def __init__(self, transport: HttpTransport, base_url: str) -> None:
        self._transport = transport
        self._base_url = base_url.rstrip("/")

    async def fetch(self, instrument: Instrument, range_: str) -> ChartResult:
        payload = await self._transport.get_json(
            f"{self._base_url}/v8/finance/chart/{instrument.symbol}",
            {"range": range_, "interval": "1d"},
        )
        chart = payload.get("chart")
        if not isinstance(chart, dict):
            raise DeliveryError("Yahoo returned no chart.", details={"symbol": instrument.symbol})
        results = chart.get("result")
        if not isinstance(results, list) or not results or not isinstance(results[0], dict):
            raise DeliveryError("Yahoo returned no result.", details={"symbol": instrument.symbol})

        result: dict[str, Any] = results[0]
        meta = result.get("meta")
        if not isinstance(meta, dict):
            raise DeliveryError("Yahoo returned no meta.", details={"symbol": instrument.symbol})

        price = meta.get("regularMarketPrice")
        if price is None:
            raise DeliveryError("Yahoo returned no price.", details={"symbol": instrument.symbol})

        currency = str(meta.get("currency") or instrument.quote_currency).upper()
        history = self._history(result)

        return ChartResult(
            symbol=instrument.symbol,
            currency=currency,
            unit_price_minor=to_minor_units(price, field="regularMarketPrice"),
            previous_close_minor=self._previous_close(meta, history),
            as_of=self._meta_time(meta),
            history=history,
        )

    def _previous_close(
        self, meta: dict[str, Any], history: list[HistoryPoint]
    ) -> int | None:
        if len(history) >= 2:
            return history[-2].unit_price_minor
        quoted = meta.get("regularMarketPreviousClose", meta.get("previousClose"))
        if quoted is None:
            return None
        return to_minor_units(quoted, field="previousClose")

    def _meta_time(self, meta: dict[str, Any]) -> datetime:
        stamp = meta.get("regularMarketTime")
        if stamp is None:
            return datetime.now(timezone.utc)
        return datetime.fromtimestamp(int(stamp), tz=timezone.utc)

    def _history(self, result: dict[str, Any]) -> list[HistoryPoint]:
        stamps = result.get("timestamp")
        indicators = result.get("indicators")
        if not isinstance(stamps, list) or not isinstance(indicators, dict):
            return []
        quotes = indicators.get("quote")
        if not isinstance(quotes, list) or not quotes or not isinstance(quotes[0], dict):
            return []
        closes = quotes[0].get("close")
        if not isinstance(closes, list):
            return []

        points: list[HistoryPoint] = []
        for stamp, close in zip(stamps, closes):
            if close is None or stamp is None:
                continue
            points.append(
                HistoryPoint(
                    on=epoch_to_date(stamp, field="timestamp"),
                    unit_price_minor=to_minor_units(close, field="close"),
                )
            )
        return points


class FrankfurterRateClient:
    def __init__(self, transport: HttpTransport, base_url: str) -> None:
        self._transport = transport
        self._base_url = base_url.rstrip("/")

    async def fetch(self, base: str, quote: str) -> RateResult:
        payload = await self._transport.get_json(
            f"{self._base_url}/latest",
            {"base": base, "symbols": quote},
        )
        rates = payload.get("rates")
        if not isinstance(rates, dict) or quote not in rates:
            raise DeliveryError(
                "Frankfurter returned no rate for that pair.",
                details={"base": base, "quote": quote},
            )
        stamp = payload.get("date")
        return RateResult(
            base=base,
            quote=quote,
            rate_micro=to_rate_micro(rates[quote], field="rate"),
            as_of=date.fromisoformat(str(stamp)) if stamp else datetime.now(timezone.utc).date(),
        )

    async def fetch_series(
        self, base: str, quote: str, start: date, end: date
    ) -> dict[date, int]:
        payload = await self._transport.get_json(
            f"{self._base_url}/{start.isoformat()}..{end.isoformat()}",
            {"base": base, "symbols": quote},
        )
        rates = payload.get("rates")
        if not isinstance(rates, dict) or not rates:
            raise DeliveryError(
                "Frankfurter returned no series for that pair.",
                details={"base": base, "quote": quote},
            )

        series: dict[date, int] = {}
        for day, values in rates.items():
            if not isinstance(values, dict) or quote not in values:
                continue
            series[date.fromisoformat(str(day))] = to_rate_micro(values[quote], field="rate")
        if not series:
            raise DeliveryError(
                "Frankfurter returned an empty series.",
                details={"base": base, "quote": quote},
            )
        return series
