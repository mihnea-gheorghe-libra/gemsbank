import asyncio
import logging
from bisect import bisect_right
from datetime import date, datetime
from functools import lru_cache
from typing import Any, ClassVar, Protocol

from motor.motor_asyncio import AsyncIOMotorClientSession

from backend.accounts.account import Account, AccountKind, AccountStatus
from backend.accounts.service import AccountsService, get_accounts_service
from backend.command_bus import Command, CommandBus, CommandResult, bus
from backend.config import Settings, settings
from backend.database.records import AuditRecord, DomainEvent
from backend.database.repositories import MongoInvestmentOrderRepository
from backend.helpers.context import ActorContext, log_event
from backend.helpers.errors import DomainError, NotFoundError, ValidationError
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
from backend.investments.order import InvestmentOrder, OrderSide
from backend.investments.validation import (
    convert_minor,
    holding_value_minor,
    normalise_range,
    to_quantity_micro,
)
from backend.ledger.journal import HouseAccount, TransactionKind, house_account_id
from backend.ledger.service import LedgerService, get_ledger_service
from backend.ledger.validation import validate_minor_units

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


class OrderRepository(Protocol):
    async def append(
        self, order: InvestmentOrder, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def holdings_for_account(self, account_id: str) -> dict[str, int]: ...

    async def list_for_account(self, account_id: str) -> list[InvestmentOrder]: ...


class BuyInstrument(Command):
    command_name: ClassVar[str] = "investments.buy"

    account_id: str
    instrument_id: str
    amount_minor: int


class SellInstrument(Command):
    command_name: ClassVar[str] = "investments.sell"

    account_id: str
    instrument_id: str
    amount_minor: int


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
        orders: OrderRepository,
        accounts: AccountsService,
        ledger: LedgerService,
        catalogue: tuple[Instrument, ...] = CATALOGUE,
    ) -> None:
        self._charts = charts
        self._rates = rates
        self._clock = clock
        self._config = config
        self._orders = orders
        self._accounts = accounts
        self._ledger = ledger
        self._catalogue = catalogue
        self._lock = asyncio.Lock()
        self._snapshots: dict[str, MarketSnapshot] = {}
        self._last_charts: dict[str, ChartResult] = {}
        self._last_rates: dict[str, RateResult] = {}
        self._last_series: dict[str, dict[date, int]] = {}

    def register(self, command_bus: CommandBus) -> None:
        command_bus.register(BuyInstrument, self._handle_buy)
        command_bus.register(SellInstrument, self._handle_sell)

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
        snapshot = await self._current_snapshot(range_, force)
        return snapshot.public_view()

    async def _current_snapshot(
        self, range_: str | None = None, force: bool = False
    ) -> MarketSnapshot:
        window = normalise_range(range_)
        async with self._lock:
            cached = self._snapshots.get(window)
            if cached is not None and not self._may_refresh(cached, force):
                return cached
            snapshot = await self._build(window)
            self._snapshots[window] = snapshot
            return snapshot

    async def _quote_for(self, instrument_id: str) -> Quote:
        if not any(item.id == instrument_id for item in self._catalogue):
            raise NotFoundError(
                "That instrument does not exist.", details={"field": "instrumentId"}
            )
        snapshot = await self._current_snapshot()
        quote = next(
            (item for item in snapshot.quotes if item.instrument_id == instrument_id), None
        )
        if quote is None:
            raise ValidationError(
                "No live price is available for this instrument right now.",
                details={"field": "instrumentId"},
            )
        return quote

    async def _resolve_investment_account(self, account_id: str, user_id: str) -> Account:
        account = await self._accounts.get_owned(account_id, user_id)
        if account.kind is not AccountKind.INVEST:
            raise ValidationError(
                "That is not an investment account.", details={"field": "accountId"}
            )
        return account

    async def _to_display_amount(self, amount_minor: int, currency: str) -> int:
        if currency == DISPLAY_CURRENCY:
            return amount_minor
        rate = await self._rates.fetch(currency, DISPLAY_CURRENCY)
        return convert_minor(amount_minor, rate.rate_micro)

    async def _handle_buy(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, BuyInstrument)
        user_id = context.actor.id
        amount = validate_minor_units(command.amount_minor)
        account = await self._resolve_investment_account(command.account_id, user_id)
        account.guard_can_send()
        quote = await self._quote_for(command.instrument_id)

        balance = await self._ledger.balance_of(account.id)
        account.guard_sufficient(balance, amount)
        held_before = await self._orders.holdings_for_account(account.id)
        display_amount = await self._to_display_amount(amount, account.currency)
        quantity_micro = to_quantity_micro(display_amount, quote.unit_price_minor)

        transaction = await self._ledger.post_transaction(
            currency=account.currency,
            kind=TransactionKind.INVESTMENT_BUY,
            legs=[
                (account.id, -amount),
                (house_account_id(HouseAccount.INVEST_SUSPENSE, account.currency), amount),
            ],
            reference=f"Cumpărare {quote.symbol}",
            counterparty="GEMS Investments",
            category="investment",
            correlation_id=context.correlation_id,
            actor=context.actor.label(),
            session=session,
        )

        order = InvestmentOrder(
            user_id=user_id,
            account_id=account.id,
            instrument_id=command.instrument_id,
            side=OrderSide.BUY,
            quantity_micro=quantity_micro,
            unit_price_minor=quote.unit_price_minor,
            amount_minor=amount,
            currency=account.currency,
            journal_transaction_id=transaction.id,
            executed_at=self._clock.now(),
        )
        await self._orders.append(order, session=session)

        view = order.public_view() | {
            "accountBalanceMinor": balance - amount,
            "holdingQuantityMicro": held_before.get(command.instrument_id, 0) + quantity_micro,
        }
        return CommandResult(
            data=view,
            audit=AuditRecord(
                action="investments.bought",
                entity_type="investmentOrder",
                entity_id=order.id,
                after=view,
            ),
            events=[
                DomainEvent(
                    name="investments.bought",
                    aggregate_type="investmentOrder",
                    aggregate_id=order.id,
                    payload={
                        "userId": user_id,
                        "accountId": account.id,
                        "instrumentId": command.instrument_id,
                        "quantityMicro": quantity_micro,
                        "amountMinor": amount,
                    },
                )
            ],
        )

    async def _handle_sell(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, SellInstrument)
        user_id = context.actor.id
        amount = validate_minor_units(command.amount_minor)
        account = await self._resolve_investment_account(command.account_id, user_id)
        account.guard_can_receive()
        quote = await self._quote_for(command.instrument_id)

        display_amount = await self._to_display_amount(amount, account.currency)
        quantity_micro = to_quantity_micro(display_amount, quote.unit_price_minor)
        held_before = await self._orders.holdings_for_account(account.id)
        held = held_before.get(command.instrument_id, 0)
        if quantity_micro > held:
            raise ValidationError(
                "You don't hold that many units.",
                details={"field": "amountMinor", "heldQuantityMicro": held},
            )

        balance = await self._ledger.balance_of(account.id)
        transaction = await self._ledger.post_transaction(
            currency=account.currency,
            kind=TransactionKind.INVESTMENT_SELL,
            legs=[
                (house_account_id(HouseAccount.INVEST_SUSPENSE, account.currency), -amount),
                (account.id, amount),
            ],
            reference=f"Vânzare {quote.symbol}",
            counterparty="GEMS Investments",
            category="investment",
            correlation_id=context.correlation_id,
            actor=context.actor.label(),
            session=session,
        )

        order = InvestmentOrder(
            user_id=user_id,
            account_id=account.id,
            instrument_id=command.instrument_id,
            side=OrderSide.SELL,
            quantity_micro=quantity_micro,
            unit_price_minor=quote.unit_price_minor,
            amount_minor=amount,
            currency=account.currency,
            journal_transaction_id=transaction.id,
            executed_at=self._clock.now(),
        )
        await self._orders.append(order, session=session)

        view = order.public_view() | {
            "accountBalanceMinor": balance + amount,
            "holdingQuantityMicro": held - quantity_micro,
        }
        return CommandResult(
            data=view,
            audit=AuditRecord(
                action="investments.sold",
                entity_type="investmentOrder",
                entity_id=order.id,
                after=view,
            ),
            events=[
                DomainEvent(
                    name="investments.sold",
                    aggregate_type="investmentOrder",
                    aggregate_id=order.id,
                    payload={
                        "userId": user_id,
                        "accountId": account.id,
                        "instrumentId": command.instrument_id,
                        "quantityMicro": quantity_micro,
                        "amountMinor": amount,
                    },
                )
            ],
        )

    async def portfolio(self, user_id: str) -> dict[str, Any]:
        accounts = [
            account
            for account in await self._accounts.owned_accounts(user_id)
            if account.kind is AccountKind.INVEST and account.status is AccountStatus.ACTIVE and account.currency == "RON"
        ]
        if not accounts:
            raise NotFoundError(
                "Open an investment account first.", details={"field": "accountId"}
            )

        snapshot = await self._current_snapshot()
        quotes_by_instrument = {quote.instrument_id: quote for quote in snapshot.quotes}
        instruments_by_id = {item.id: item for item in self._catalogue}
        balances = await self._ledger.balances_of([account.id for account in accounts])

        account_views = []
        for account in accounts:
            held = await self._orders.holdings_for_account(account.id)
            holdings = []
            for instrument_id, quantity_micro in held.items():
                quote = quotes_by_instrument.get(instrument_id)
                instrument = instruments_by_id.get(instrument_id)
                if quote is None or instrument is None:
                    continue
                holdings.append(
                    {
                        "instrumentId": instrument_id,
                        "symbol": instrument.symbol,
                        "name": instrument.name,
                        "assetClass": instrument.asset_class.value,
                        "unitKey": instrument.unit_key,
                        "quantityMicro": quantity_micro,
                        "unitPriceMinor": quote.unit_price_minor,
                        "valueMinor": holding_value_minor(quantity_micro, quote.unit_price_minor),
                        "currency": snapshot.currency,
                        "changeBps": quote.change_bps(),
                    }
                )
            account_views.append(
                {
                    "accountId": account.id,
                    "currency": account.currency,
                    "cashBalanceMinor": balances.get(account.id, 0),
                    "holdings": holdings,
                }
            )

        return {
            "accounts": account_views,
            "asOf": snapshot.refreshed_at.isoformat(),
            "live": snapshot.live,
        }

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
    service = InvestmentsService(
        charts=YahooChartClient(transport, settings.yahoo_chart_base_url),
        rates=FrankfurterRateClient(transport, settings.frankfurter_base_url),
        clock=SystemClock(),
        config=settings,
        orders=MongoInvestmentOrderRepository(),
        accounts=get_accounts_service(),
        ledger=get_ledger_service(),
    )
    service.register(bus)
    return service


async def close_investments_clients() -> None:
    await get_investments_transport().aclose()
