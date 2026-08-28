from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from backend.accounts.account import Account, AccountKind
from backend.accounts.service import AccountsService
from backend.config import settings
from backend.helpers.context import Actor, ActorContext
from backend.helpers.errors import NotFoundError, ValidationError
from backend.investments.adapters import ChartResult, RateResult
from backend.investments.instrument import AssetClass, Instrument
from backend.investments.order import InvestmentOrder, OrderSide
from backend.investments.service import (
    BuyInstrument,
    InvestmentsService,
    SellInstrument,
)
from backend.ledger.service import LedgerService

TEST_CATALOGUE: tuple[Instrument, ...] = (
    Instrument(
        id="h-test",
        symbol="TEST",
        name="Test ETF",
        asset_class=AssetClass.FUND,
        unit_key="units",
        quote_currency="RON",
        fallback_unit_price_minor=1_000,
    ),
)


class _FakeAccountRepository:
    def __init__(self, accounts: list[Account]) -> None:
        self._accounts = {account.id: account for account in accounts}

    async def add(self, account, session=None) -> None:
        self._accounts[account.id] = account

    async def get(self, account_id: str) -> Account | None:
        return self._accounts.get(account_id)

    async def get_by_iban(self, iban: str) -> Account | None:
        return next((a for a in self._accounts.values() if a.iban == iban), None)

    async def list_for_user(self, user_id: str) -> list[Account]:
        return [a for a in self._accounts.values() if a.user_id == user_id]

    async def set_status(self, account_id: str, status, session=None) -> bool:
        account = self._accounts.get(account_id)
        if account is None:
            return False
        self._accounts[account_id] = account.model_copy(update={"status": status})
        return True


class _FakeJournalRepository:
    def __init__(self, balances: dict[str, int]) -> None:
        self._balances = dict(balances)

    async def append(self, transaction, session=None) -> None:
        for entry in transaction.entries:
            self._balances[entry.account_id] = (
                self._balances.get(entry.account_id, 0) + entry.amount
            )

    async def balances_for(self, account_ids: list[str]) -> dict[str, int]:
        return {account_id: self._balances.get(account_id, 0) for account_id in account_ids}

    async def page_for(self, *args, **kwargs):
        raise NotImplementedError

    async def debited_since(self, account_ids, since) -> int:
        raise NotImplementedError

    async def count_for(self, account_ids) -> int:
        return 0

    async def in_range_for(self, *args, **kwargs):
        raise NotImplementedError

    async def balance_before(self, account_ids, before) -> int:
        return 0


class _FakeUserDirectory:
    async def get(self, user_id: str):
        return SimpleNamespace(display_name="Test User")


class _FakeOrderRepository:
    def __init__(self) -> None:
        self.orders: list[InvestmentOrder] = []

    async def append(self, order: InvestmentOrder, session=None) -> None:
        self.orders.append(order)

    async def holdings_for_account(self, account_id: str) -> dict[str, int]:
        totals: dict[str, int] = {}
        for order in self.orders:
            if order.account_id != account_id:
                continue
            sign = 1 if order.side is OrderSide.BUY else -1
            totals[order.instrument_id] = (
                totals.get(order.instrument_id, 0) + sign * order.quantity_micro
            )
        return {instrument_id: qty for instrument_id, qty in totals.items() if qty > 0}

    async def list_for_account(self, account_id: str) -> list[InvestmentOrder]:
        return [order for order in self.orders if order.account_id == account_id]


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class _FixedChartSource:
    def __init__(self, unit_price_minor: int) -> None:
        self._unit_price_minor = unit_price_minor

    async def fetch(self, instrument, range_) -> ChartResult:
        return ChartResult(
            symbol=instrument.symbol,
            currency=instrument.quote_currency,
            unit_price_minor=self._unit_price_minor,
            previous_close_minor=None,
            as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
            history=[],
        )


class _UnusedRateSource:
    async def fetch(self, base: str, quote: str):
        raise AssertionError("a RON-quoted instrument needs no FX rate")

    async def fetch_series(self, base: str, quote: str, start: date, end: date):
        raise AssertionError("a RON-quoted instrument needs no FX rate")


class _FixedRateSource:
    def __init__(self, rate_micro: int) -> None:
        self._rate_micro = rate_micro

    async def fetch(self, base: str, quote: str) -> RateResult:
        return RateResult(
            base=base, quote=quote, rate_micro=self._rate_micro, as_of=date(2026, 1, 1)
        )

    async def fetch_series(self, base: str, quote: str, start: date, end: date):
        raise AssertionError("not used by these tests")


def _account(
    user_id: str = "user-1", kind: AccountKind = AccountKind.INVEST, currency: str = "RON"
) -> Account:
    return Account(
        user_id=user_id,
        iban="RO00TESTBANK0000000001",
        holder_name="Test User",
        currency=currency,
        kind=kind,
        label="Cont investiții",
    )


def _context(user_id: str = "user-1") -> ActorContext:
    return ActorContext(actor=Actor(kind="user", id=user_id), correlation_id="corr-1")


def _build_service(
    account: Account,
    balance_minor: int,
    unit_price_minor: int = 1_000,
    rates=None,
) -> tuple[InvestmentsService, _FakeOrderRepository, LedgerService]:
    account_repo = _FakeAccountRepository([account])
    ledger = LedgerService(
        journal=_FakeJournalRepository({account.id: balance_minor}),
        clock=_FixedClock(datetime(2026, 1, 1, tzinfo=timezone.utc)),
    )
    accounts_service = AccountsService(
        accounts=account_repo,
        ledger=ledger,
        users=_FakeUserDirectory(),
        clock=_FixedClock(datetime(2026, 1, 1, tzinfo=timezone.utc)),
    )
    orders = _FakeOrderRepository()
    service = InvestmentsService(
        charts=_FixedChartSource(unit_price_minor),
        rates=rates or _UnusedRateSource(),
        clock=_FixedClock(datetime(2026, 1, 1, tzinfo=timezone.utc)),
        config=settings,
        orders=orders,
        accounts=accounts_service,
        ledger=ledger,
        catalogue=TEST_CATALOGUE,
    )
    return service, orders, ledger


async def test_buy_moves_cash_from_the_account_into_the_invest_suspense_leg() -> None:
    account = _account()
    service, orders, ledger = _build_service(account, balance_minor=100_000, unit_price_minor=1_000)
    context = _context()

    result = await service._handle_buy(
        BuyInstrument(account_id=account.id, instrument_id="h-test", amount_minor=10_000),
        context,
        session=None,
    )

    assert result.data["accountBalanceMinor"] == 90_000
    assert result.data["quantityMicro"] == 10_000_000
    assert result.data["holdingQuantityMicro"] == 10_000_000
    assert await ledger.balance_of(account.id) == 90_000
    assert len(orders.orders) == 1
    assert orders.orders[0].side is OrderSide.BUY


async def test_buy_rejects_an_amount_larger_than_the_account_holds() -> None:
    account = _account()
    service, _, _ = _build_service(account, balance_minor=1_000, unit_price_minor=1_000)
    context = _context()

    with pytest.raises(ValidationError):
        await service._handle_buy(
            BuyInstrument(account_id=account.id, instrument_id="h-test", amount_minor=10_000),
            context,
            session=None,
        )


async def test_buy_rejects_an_account_that_is_not_an_investment_account() -> None:
    account = _account(kind=AccountKind.CURRENT)
    service, _, _ = _build_service(account, balance_minor=100_000)
    context = _context()

    with pytest.raises(ValidationError):
        await service._handle_buy(
            BuyInstrument(account_id=account.id, instrument_id="h-test", amount_minor=10_000),
            context,
            session=None,
        )


async def test_buy_rejects_an_account_that_does_not_belong_to_the_user() -> None:
    account = _account(user_id="someone-else")
    service, _, _ = _build_service(account, balance_minor=100_000)
    context = _context(user_id="user-1")

    with pytest.raises(NotFoundError):
        await service._handle_buy(
            BuyInstrument(account_id=account.id, instrument_id="h-test", amount_minor=10_000),
            context,
            session=None,
        )


async def test_sell_moves_cash_back_and_reduces_the_holding() -> None:
    account = _account()
    service, orders, ledger = _build_service(account, balance_minor=100_000, unit_price_minor=1_000)
    context = _context()
    await service._handle_buy(
        BuyInstrument(account_id=account.id, instrument_id="h-test", amount_minor=10_000),
        context,
        session=None,
    )

    result = await service._handle_sell(
        SellInstrument(account_id=account.id, instrument_id="h-test", amount_minor=4_000),
        context,
        session=None,
    )

    assert result.data["accountBalanceMinor"] == 94_000
    assert result.data["holdingQuantityMicro"] == 6_000_000
    assert await ledger.balance_of(account.id) == 94_000
    assert len(orders.orders) == 2


async def test_sell_rejects_more_units_than_are_held() -> None:
    account = _account()
    service, _, _ = _build_service(account, balance_minor=100_000, unit_price_minor=1_000)
    context = _context()
    await service._handle_buy(
        BuyInstrument(account_id=account.id, instrument_id="h-test", amount_minor=5_000),
        context,
        session=None,
    )

    with pytest.raises(ValidationError):
        await service._handle_sell(
            SellInstrument(account_id=account.id, instrument_id="h-test", amount_minor=10_000),
            context,
            session=None,
        )


async def test_buy_in_a_non_ron_account_prices_units_off_the_ron_equivalent_spend() -> None:
    account = _account(currency="EUR")
    service, orders, ledger = _build_service(
        account, balance_minor=100_000, unit_price_minor=1_000, rates=_FixedRateSource(5_000_000)
    )
    context = _context()

    result = await service._handle_buy(
        BuyInstrument(account_id=account.id, instrument_id="h-test", amount_minor=2_000),
        context,
        session=None,
    )

    # 20.00 EUR spent at 1 EUR = 5.00 RON is 100.00 RON, priced against a 10.00 RON unit.
    assert result.data["quantityMicro"] == 10_000_000
    assert result.data["accountBalanceMinor"] == 98_000
    assert await ledger.balance_of(account.id) == 98_000
    assert orders.orders[0].currency == "EUR"
    assert orders.orders[0].amount_minor == 2_000


async def test_sell_in_a_non_ron_account_prices_units_off_the_ron_equivalent_proceeds() -> None:
    account = _account(currency="EUR")
    service, _orders, ledger = _build_service(
        account, balance_minor=100_000, unit_price_minor=1_000, rates=_FixedRateSource(5_000_000)
    )
    context = _context()
    await service._handle_buy(
        BuyInstrument(account_id=account.id, instrument_id="h-test", amount_minor=2_000),
        context,
        session=None,
    )

    result = await service._handle_sell(
        SellInstrument(account_id=account.id, instrument_id="h-test", amount_minor=800),
        context,
        session=None,
    )

    # 8.00 EUR at 1 EUR = 5.00 RON is 40.00 RON, i.e. 4 of the 10 units held;
    # the account itself is still credited the 8.00 EUR that was actually sold.
    assert result.data["holdingQuantityMicro"] == 6_000_000
    assert result.data["accountBalanceMinor"] == 98_800
    assert await ledger.balance_of(account.id) == 98_800


async def test_portfolio_requires_an_investment_account() -> None:
    account = _account(kind=AccountKind.CURRENT)
    service, _, _ = _build_service(account, balance_minor=0)

    with pytest.raises(NotFoundError):
        await service.portfolio("user-1")


async def test_portfolio_lists_holdings_for_the_investment_account() -> None:
    account = _account()
    service, _, _ = _build_service(account, balance_minor=100_000, unit_price_minor=1_000)
    context = _context()
    await service._handle_buy(
        BuyInstrument(account_id=account.id, instrument_id="h-test", amount_minor=10_000),
        context,
        session=None,
    )

    portfolio = await service.portfolio("user-1")

    assert len(portfolio["accounts"]) == 1
    account_view = portfolio["accounts"][0]
    assert account_view["accountId"] == account.id
    assert account_view["cashBalanceMinor"] == 90_000
    assert account_view["holdings"] == [
        {
            "instrumentId": "h-test",
            "symbol": "TEST",
            "name": "Test ETF",
            "assetClass": "fund",
            "unitKey": "units",
            "quantityMicro": 10_000_000,
            "unitPriceMinor": 1_000,
            "valueMinor": 10_000,
            "currency": "RON",
            "changeBps": None,
        }
    ]
