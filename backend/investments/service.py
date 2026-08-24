import asyncio
import logging
from bisect import bisect_right
from datetime import date, datetime
from functools import lru_cache
from typing import Any, Protocol

from backend.config import Settings, settings
from backend.helpers.context import log_event
from backend.helpers.errors import DomainError
from backend.investments.adapters import (
    CATALOGUE,
    FALLBACK_RATES,
    ChartResult,
    FrankfurterRateClient,
    HttpTransport,
    RateResult,
    SystemClock,
    YahooChartClient,
)
from backend.investments.instrument import (
    ExchangeRate,
    HistoryPoint,
    Instrument,
    MarketSnapshot,
    Quote,
)
from backend.investments.validation import convert_minor, normalise_range

logger = logging.getLogger(__name__)

DISPLAY_CURRENCY = "RON"
IDENTITY_RATE_MICRO = 1_000_000


class ChartSource(Protocol):
    async def fetch(self, instrument: Instrument, range_: str) -> ChartResult: ...


class RateSource(Protocol):
    async def fetch(self, base: str, quote: str) -> RateResult: ...

    async def fetch_series(
        self, base: str, quote: str, start: date, end: date
    ) -> dict[date, int]: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class _ResolvedRate:
    def __init__(self, rate: ExchangeRate, series: dict[date, int]) -> None:
        self.rate = rate
        self.series = series
        self._days = sorted(series)

    def at(self, on: date) -> int:
        if not self._days:
            return self.rate.rate_micro
        position = bisect_right(self._days, on)
        if position == 0:
            return self.series[self._days[0]]
        return self.series[self._days[position - 1]]


class InvestmentsService:
    def __init__(
        self,
        charts: ChartSource,
        rates: RateSource,
        clock: Clock,
        config: Settings,
        catalogue: tuple[Instrument, ...] = CATALOGUE,
    ) -> None:
        self._charts = charts
        self._rates = rates
        self._clock = clock
        self._config = config
        self._catalogue = catalogue
        self._lock = asyncio.Lock()
        self._snapshots: dict[str, MarketSnapshot] = {}
        self._last_charts: dict[str, ChartResult] = {}
        self._last_rates: dict[str, RateResult] = {}
        self._last_series: dict[str, dict[date, int]] = {}

    def instruments(self) -> dict[str, Any]:
        return {
            "currency": DISPLAY_CURRENCY,
            "instruments": [
                {
                    "id": item.id,
                    "symbol": item.symbol,
                    "name": item.name,
                    "assetClass": item.asset_class.value,
                    "unitKey": item.unit_key,
                    "quoteCurrency": item.quote_currency,
                }
                for item in self._catalogue
            ],
        }

    async def market(self, range_: str | None = None, force: bool = False) -> dict[str, Any]:
        window = normalise_range(range_)
        async with self._lock:
            cached = self._snapshots.get(window)
            if cached is not None and not self._may_refresh(cached, force):
                return cached.public_view()
            snapshot = await self._build(window)
            self._snapshots[window] = snapshot
            return snapshot.public_view()

    def _may_refresh(self, snapshot: MarketSnapshot, force: bool) -> bool:
        age = (self._clock.now() - snapshot.refreshed_at).total_seconds()
        if force:
            return age >= self._config.investments_min_refresh_seconds
        return not self._still_fresh(snapshot)

    def _still_fresh(self, snapshot: MarketSnapshot) -> bool:
        age = (self._clock.now() - snapshot.refreshed_at).total_seconds()
        ttl = (
            self._config.investments_quote_ttl_seconds
            if snapshot.live
            else self._config.investments_retry_seconds
        )
        return age < ttl

    async def _build(self, window: str) -> MarketSnapshot:
        resolved = await self._resolve_rates()
        quotes: list[Quote] = []
        live = all(item.rate.live for item in resolved.values())

        for instrument in self._catalogue:
            chart, fresh = await self._resolve_chart(instrument, window)
            live = live and fresh
            quotes.append(self._to_quote(instrument, chart, fresh, resolved))

        return MarketSnapshot(
            currency=DISPLAY_CURRENCY,
            quotes=quotes,
            rates=[item.rate for item in resolved.values()],
            refreshed_at=self._clock.now(),
            live=live,
        )

    async def _resolve_rates(self) -> dict[str, _ResolvedRate]:
        bases = {
            item.quote_currency
            for item in self._catalogue
            if item.quote_currency != DISPLAY_CURRENCY
        }
        resolved: dict[str, _ResolvedRate] = {}
        for base in sorted(bases):
            resolved[base] = await self._resolve_rate(base)
        return resolved

    async def _resolve_rate(self, base: str) -> _ResolvedRate:
        today = self._clock.now().date()
        fresh = True
        try:
            latest = await self._rates.fetch(base, DISPLAY_CURRENCY)
            self._last_rates[base] = latest
        except DomainError as exc:
            fresh = False
            self._note_outage("investments.rate_unavailable", base=base, reason=str(exc))
            latest = self._last_rates.get(base) or RateResult(
                base=base,
                quote=DISPLAY_CURRENCY,
                rate_micro=FALLBACK_RATES.get(base, IDENTITY_RATE_MICRO),
                as_of=today,
            )

        series = self._last_series.get(base, {})
        try:
            series = await self._rates.fetch_series(
                base, DISPLAY_CURRENCY, self._series_start(), today
            )
            self._last_series[base] = series
        except DomainError as exc:
            self._note_outage("investments.rate_series_unavailable", base=base, reason=str(exc))

        return _ResolvedRate(
            ExchangeRate(
                base=base,
                quote=DISPLAY_CURRENCY,
                rate_micro=latest.rate_micro,
                as_of=latest.as_of,
                live=fresh,
            ),
            series,
        )

    def _series_start(self) -> date:
        now = self._clock.now().date()
        days = self._config.investments_series_days
        return date.fromordinal(max(1, now.toordinal() - days))

    async def _resolve_chart(
        self, instrument: Instrument, window: str
    ) -> tuple[ChartResult, bool]:
        try:
            chart = await self._charts.fetch(instrument, window)
            self._last_charts[instrument.id] = chart
            return chart, True
        except DomainError as exc:
            self._note_outage(
                "investments.quote_unavailable", symbol=instrument.symbol, reason=str(exc)
            )

        remembered = self._last_charts.get(instrument.id)
        if remembered is not None:
            return remembered, False

        return (
            ChartResult(
                symbol=instrument.symbol,
                currency=instrument.quote_currency,
                unit_price_minor=instrument.fallback_unit_price_minor,
                previous_close_minor=None,
                as_of=self._clock.now(),
                history=[],
            ),
            False,
        )

    def _to_quote(
        self,
        instrument: Instrument,
        chart: ChartResult,
        fresh: bool,
        resolved: dict[str, _ResolvedRate],
    ) -> Quote:
        pair = resolved.get(chart.currency)
        spot = pair.rate.rate_micro if pair else IDENTITY_RATE_MICRO

        history = [
            HistoryPoint(
                on=point.on,
                unit_price_minor=convert_minor(
                    point.unit_price_minor, pair.at(point.on) if pair else IDENTITY_RATE_MICRO
                ),
            )
            for point in chart.history
        ]

        return Quote(
            instrument_id=instrument.id,
            symbol=instrument.symbol,
            name=instrument.name,
            asset_class=instrument.asset_class,
            unit_key=instrument.unit_key,
            quote_currency=chart.currency,
            quote_unit_price_minor=chart.unit_price_minor,
            currency=DISPLAY_CURRENCY,
            unit_price_minor=convert_minor(chart.unit_price_minor, spot),
            previous_close_minor=(
                None
                if chart.previous_close_minor is None
                else convert_minor(chart.previous_close_minor, spot)
            ),
            as_of=chart.as_of,
            live=fresh,
            history=history,
        )

    def _note_outage(self, message: str, **context: object) -> None:
        log_event(logger, message, **context)


@lru_cache(maxsize=1)
def get_investments_transport() -> HttpTransport:
    return HttpTransport(settings.investments_timeout_seconds)


@lru_cache(maxsize=1)
def get_investments_service() -> InvestmentsService:
    transport = get_investments_transport()
    return InvestmentsService(
        charts=YahooChartClient(transport, settings.yahoo_chart_base_url),
        rates=FrankfurterRateClient(transport, settings.frankfurter_base_url),
        clock=SystemClock(),
        config=settings,
    )


async def close_investments_clients() -> None:
    await get_investments_transport().aclose()
