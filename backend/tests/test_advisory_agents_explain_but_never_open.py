import asyncio

import pytest
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from backend.agents.credits import CreditsAgent
from backend.agents.deposits import DepositsAgent
from backend.agents.investments import InvestmentsAgent
from backend.capabilities import investments as inv_caps
from backend.capabilities import products as prod_caps
from backend.capabilities.registry import Capability, CapabilityRegistry, SideEffect
from backend.helpers.context import Actor

ACTOR = Actor(kind="agent", id="investments-agent", on_behalf_of="user-1")


class _EmptyIn(BaseModel):
    pass


class _EmptyOut(BaseModel):
    ok: bool = True


async def _never(actor, payload):
    raise AssertionError("must not be reachable")


def _registry_with_a_money_door() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    for name, effect in [
        ("investments.market.get", SideEffect.READ),
        ("deposits.products.list", SideEffect.READ),
        ("deposits.maturity.estimate", SideEffect.READ),
        ("credits.products.list", SideEffect.READ),
        ("credits.repayment.estimate", SideEffect.READ),
        ("payments.balances.get", SideEffect.READ),
        ("payments.transfer.propose", SideEffect.MONEY_MOVING),
        ("accounts.open", SideEffect.WRITE),
    ]:
        registry.register(
            Capability(
                name=name,
                input_schema=_EmptyIn,
                output_schema=_EmptyOut,
                side_effect=effect,
                required_scope="test",
                resolver=_never,
            )
        )
    return registry


async def _noop_audit(record, actor, correlation_id) -> None:
    return None


def _offered(agent_cls):
    agent = agent_cls(chat=None, capabilities=_registry_with_a_money_door(), audit=_noop_audit)
    return {tool["function"]["name"] for tool in agent._tool_defs()}, agent


@pytest.mark.parametrize(
    "agent_cls,expected",
    [
        (InvestmentsAgent, {"investments.market.get", "payments.balances.get"}),
        (
            DepositsAgent,
            {"deposits.products.list", "deposits.maturity.estimate", "payments.balances.get"},
        ),
        (
            CreditsAgent,
            {"credits.products.list", "credits.repayment.estimate", "payments.balances.get"},
        ),
    ],
)
def test_each_advisory_agent_sees_only_its_own_reads(agent_cls, expected) -> None:
    offered, agent = _offered(agent_cls)
    assert offered == expected
    assert "payments.transfer.propose" not in offered
    assert "accounts.open" not in offered
    assert agent.proposal_tool_names == frozenset()


def test_no_advisory_agent_can_ever_be_handed_the_money_door() -> None:
    for agent_cls in (InvestmentsAgent, DepositsAgent, CreditsAgent):
        _, agent = _offered(agent_cls)
        capability = agent._capabilities.get("payments.transfer.propose")
        assert agent._may_call(capability) is False


def _maturity(**kwargs):
    return asyncio.run(
        prod_caps.resolve_maturity_estimate(ACTOR, prod_caps.MaturityInput(**kwargs))
    )


def _repayment(**kwargs):
    return asyncio.run(
        prod_caps.resolve_repayment_estimate(ACTOR, prod_caps.RepaymentInput(**kwargs))
    )


def test_a_deposit_estimate_is_arithmetic_the_model_never_has_to_do() -> None:
    result = _maturity(amountMinorUnits=1_000_00, months=12, rateBps=610)
    assert result.interest_minor == 6100
    assert result.interest_formatted == "61,00 RON"
    assert result.total_formatted == "1.061,00 RON"
    assert "no compounding" in result.caveat


def test_a_deposit_estimate_scales_with_the_term_not_just_the_rate() -> None:
    half = _maturity(amountMinorUnits=1_000_00, months=6, rateBps=610)
    full = _maturity(amountMinorUnits=1_000_00, months=12, rateBps=610)
    assert half.interest_minor * 2 == full.interest_minor


def test_a_deposit_estimate_reports_in_the_currency_it_was_given() -> None:
    result = _maturity(amountMinorUnits=1_000_00, months=12, rateBps=225, currency="eur")
    assert result.total_formatted.endswith("EUR")


def test_a_repayment_estimate_splits_the_total_across_the_months() -> None:
    result = _repayment(amountMinorUnits=10_000_00, months=12, rateBps=790)
    assert result.total_interest_minor == 79000
    assert result.total_repaid_minor == 1_079_000
    assert result.monthly_minor == round(1_079_000 / 12)
    assert result.monthly_formatted == "899,17 RON"


def test_an_estimate_always_carries_the_caveat_that_it_is_not_a_quote() -> None:
    assert "not a quote" in _repayment(
        amountMinorUnits=1000, months=12, rateBps=790
    ).caveat


@pytest.mark.parametrize("months", [0, 361])
def test_an_impossible_term_is_refused_before_any_arithmetic(months) -> None:
    with pytest.raises(PydanticValidationError):
        prod_caps.RepaymentInput(amountMinorUnits=1000, months=months, rateBps=790)


def test_an_absurd_rate_is_refused_rather_than_illustrated() -> None:
    with pytest.raises(PydanticValidationError):
        prod_caps.RepaymentInput(amountMinorUnits=1000, months=12, rateBps=99_999)


def test_the_deposit_catalogue_says_plainly_that_nothing_is_opened() -> None:
    result = asyncio.run(
        prod_caps.resolve_deposit_products(ACTOR, prod_caps.DepositProductsInput())
    )
    assert "not wired to the ledger" in result.note
    assert {p.id for p in result.products} == {"term", "goal"}
    assert all(term.rate_formatted.endswith("%") for p in result.products for term in p.terms)


def test_the_credit_catalogue_says_plainly_that_nothing_is_decided() -> None:
    result = asyncio.run(
        prod_caps.resolve_credit_products(ACTOR, prod_caps.CreditProductsInput())
    )
    assert "not a credit decision" in result.note
    assert {p.id for p in result.products} == {"personal", "line", "mortgage"}
    personal = next(p for p in result.products if p.id == "personal")
    assert personal.max_formatted == "150.000,00 RON"


class _FakeInvestments:
    def __init__(self, snapshot) -> None:
        self._snapshot = snapshot
        self.ranges: list[str] = []

    async def market(self, range_, force=False):
        self.ranges.append(range_)
        return self._snapshot


def _snapshot(live=True):
    return {
        "currency": "RON",
        "live": live,
        "refreshedAt": "2026-08-26T09:00:00+00:00",
        "quotes": [
            {
                "id": "h-msci",
                "symbol": "URTH",
                "name": "MSCI World ETF",
                "assetClass": "fund",
                "unitPriceMinor": 94303,
                "changeBps": 41,
                "asOf": "2026-08-25T20:00:00+00:00",
                "history": [
                    {"on": "2026-07-27", "unitPriceMinor": 92457},
                    {"on": "2026-08-25", "unitPriceMinor": 94303},
                ],
            }
        ],
    }


def _market(**kwargs):
    fake = _FakeInvestments(kwargs.pop("snapshot", _snapshot()))
    result = asyncio.run(
        inv_caps.resolve_market(ACTOR, inv_caps.MarketInput(**kwargs), investments=fake)
    )
    return result, fake


def test_prices_reach_the_model_preformatted_so_it_never_converts_them() -> None:
    result, _ = _market()
    quote = result.quotes[0]
    assert quote.unit_price_formatted == "943,03 RON"
    assert quote.change_formatted == "+0,41%"
    assert quote.period_low_formatted == "924,57 RON"
    assert quote.period_high_formatted == "943,03 RON"


def test_a_named_instrument_narrows_the_answer() -> None:
    result, _ = _market(instrumentId="h-msci")
    assert result.status == "ok"
    assert [q.id for q in result.quotes] == ["h-msci"]


def test_an_unknown_instrument_lists_the_real_ones_instead_of_guessing() -> None:
    result, _ = _market(instrumentId="h-gold")
    assert result.status == "no_match"
    assert result.quotes == []
    assert result.known_instrument_ids == ["h-msci"]


def test_stale_prices_come_with_an_instruction_to_say_so() -> None:
    result, _ = _market(snapshot=_snapshot(live=False))
    assert result.live is False
    assert "last prices" in (result.staleness_note or "")


def test_live_prices_carry_no_staleness_warning_to_repeat() -> None:
    result, _ = _market()
    assert result.staleness_note is None


def test_the_range_the_customer_asked_for_is_the_range_fetched() -> None:
    _, fake = _market(range="1mo")
    assert fake.ranges == ["1mo"]


def test_an_unsupported_range_is_refused_rather_than_silently_changed() -> None:
    with pytest.raises(PydanticValidationError):
        inv_caps.MarketInput(range="10y")


def test_the_market_capability_says_plainly_that_it_cannot_trade() -> None:
    result, _ = _market()
    assert "not wired to the ledger" in result.note
