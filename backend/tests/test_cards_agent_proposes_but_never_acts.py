import asyncio

import pytest
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from backend.agents.cards import PROPOSAL_TOOL_NAMES, TOOL_NAMES, CardsAgent
from backend.capabilities import cards as caps
from backend.capabilities.registry import Capability, CapabilityRegistry, SideEffect
from backend.helpers.context import Actor

USER_ID = "user-1"
ACTOR = Actor(kind="agent", id="cards-agent", on_behalf_of=USER_ID)


def card(card_id: str, state: str = "active", kind: str = "virtual_mastercard") -> dict:
    return {
        "cardId": card_id,
        "kind": kind,
        "numberMasked": f"•••• •••• •••• {card_id[-4:]}",
        "owner": "POPESCU ION",
        "currency": "RON",
        "expiresOn": "2030-01-31",
        "state": state,
        "atmLimitMinor": 200000,
        "onlineLimitMinor": 400000,
    }


CARDS = [card("card-4418"), card("card-1933", state="frozen", kind="physical_debit")]


class FakeCardsService:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.writes: list[str] = []

    async def list_cards(self, user_id: str) -> dict:
        assert user_id == USER_ID
        return {"cards": self._rows}

    def __getattr__(self, name):
        def _blow_up(*args, **kwargs):
            raise AssertionError(f"a proposal must never call {name}")

        return _blow_up


def _list(rows=None):
    return asyncio.run(
        caps.resolve_cards_list(
            ACTOR,
            caps.CardsListInput(),
            cards_service=FakeCardsService(rows if rows is not None else CARDS),
        )
    )


def _propose(rows=None, **kwargs):
    service = FakeCardsService(rows if rows is not None else CARDS)
    result = asyncio.run(
        caps.resolve_card_action(
            ACTOR, caps.CardActionInput(**kwargs), cards_service=service
        )
    )
    assert service.writes == []
    return result


def test_a_card_list_never_carries_a_pin_a_cvv_or_a_full_number() -> None:
    result = _list()
    assert result.status == "ok"
    fields = set(caps.CardView.model_fields)
    assert not any("pin" in f or "cvv" in f or "secret" in f for f in fields)
    for row in result.cards:
        rendered = row.model_dump_json().lower()
        for secret in ("pin", "cvv"):
            assert secret not in rendered
        assert "••••" in row.number_masked
    assert "never shown here" in result.note


def test_limits_reach_the_model_preformatted() -> None:
    result = _list()
    assert result.cards[0].atm_limit_formatted == "2.000,00 RON"
    assert result.cards[0].online_limit_formatted == "4.000,00 RON"


def test_a_customer_with_no_cards_is_told_so_rather_than_shown_nothing() -> None:
    assert _list(rows=[]).status == "no_cards"


def test_freezing_an_active_card_is_proposed_never_performed() -> None:
    result = _propose(action="freeze", cardId="card-4418")
    assert result.status == "proposed"
    assert result.requires_human_confirmation is True
    assert result.irreversible is False
    assert result.reveals_secret is False


def test_freezing_an_already_frozen_card_is_blocked_with_a_reason() -> None:
    result = _propose(action="freeze", cardId="card-1933")
    assert result.status == "blocked"
    assert "illegal_transition" in {b.code for b in result.blockers}


def test_unfreezing_only_makes_sense_on_a_frozen_card() -> None:
    assert _propose(action="unfreeze", cardId="card-1933").status == "proposed"
    assert _propose(action="unfreeze", cardId="card-4418").status == "blocked"


def test_blocking_is_flagged_irreversible_so_the_ui_can_warn() -> None:
    result = _propose(action="block", cardId="card-4418")
    assert result.status == "proposed"
    assert result.irreversible is True


def test_nothing_can_be_done_to_an_already_blocked_card() -> None:
    rows = [card("card-dead", state="blocked")]
    for action in ("freeze", "unfreeze", "block", "reveal_pin", "set_atm_limit"):
        kwargs = {"action": action, "cardId": "card-dead"}
        if action == "set_atm_limit":
            kwargs["limitMinorUnits"] = 1000
        assert _propose(rows=rows, **kwargs).status == "blocked", action


def test_a_limit_change_without_a_limit_asks_instead_of_assuming_one() -> None:
    result = _propose(action="set_atm_limit", cardId="card-4418")
    assert result.status == "needs_clarification"
    assert "limit_missing" in {b.code for b in result.blockers}


def test_a_limit_change_carries_the_new_limit_formatted() -> None:
    result = _propose(action="set_atm_limit", cardId="card-4418", limitMinorUnits=150000)
    assert result.status == "proposed"
    assert result.limit_formatted == "1.500,00 RON"


def test_a_limit_beyond_what_the_bank_allows_is_refused_before_proposing() -> None:
    with pytest.raises(PydanticValidationError):
        caps.CardActionInput(action="set_atm_limit", cardId="c", limitMinorUnits=99_999_999)


def test_an_action_without_a_card_lists_the_candidates_rather_than_picking() -> None:
    result = _propose(action="freeze")
    assert result.status == "needs_clarification"
    assert len(result.candidates) == 2
    assert "card_not_named" in {b.code for b in result.blockers}


def test_an_invented_card_id_is_refused_and_the_real_ones_offered() -> None:
    result = _propose(action="freeze", cardId="card-does-not-exist")
    assert result.status == "needs_clarification"
    assert {c.card_id for c in result.candidates} == {"card-4418", "card-1933"}


def test_issuing_a_card_needs_no_existing_card_but_still_needs_confirmation() -> None:
    for action in ("issue_virtual", "issue_physical"):
        result = _propose(rows=[], action=action)
        assert result.status == "proposed", action
        assert result.requires_human_confirmation is True


def test_revealing_a_secret_is_flagged_so_the_ui_can_gate_it() -> None:
    for action in ("reveal_pin", "reveal_details"):
        result = _propose(action=action, cardId="card-4418")
        assert result.status == "proposed", action
        assert result.reveals_secret is True


def test_a_proposal_never_contains_the_secret_it_proposes_to_reveal() -> None:
    result = _propose(action="reveal_pin", cardId="card-4418")
    dumped = result.model_dump_json().lower().replace("reveal_pin", "")
    assert "pin" not in dumped
    assert "cvv" not in dumped
    assert not any(
        f for f in caps.CardActionOutput.model_fields if "pin" in f or "cvv" in f
    )


def test_an_unknown_action_is_refused_by_the_schema() -> None:
    with pytest.raises(PydanticValidationError):
        caps.CardActionInput(action="wire_to_offshore", cardId="card-4418")


class _EmptyIn(BaseModel):
    pass


class _EmptyOut(BaseModel):
    ok: bool = True


async def _never(actor, payload):
    raise AssertionError("must not be reachable")


async def _noop_audit(record, actor, correlation_id) -> None:
    return None


def _registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    for name, effect in [
        ("cards.list", SideEffect.READ),
        ("cards.action.propose", SideEffect.WRITE),
        ("payments.transfer.propose", SideEffect.MONEY_MOVING),
        ("payments.balances.get", SideEffect.READ),
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


def test_the_cards_agent_gets_its_list_and_its_proposal_and_nothing_else() -> None:
    agent = CardsAgent(chat=None, capabilities=_registry(), audit=_noop_audit)
    offered = {tool["function"]["name"] for tool in agent._tool_defs()}
    assert offered == {"cards.list", "cards.action.propose"}
    assert "payments.transfer.propose" not in offered
    assert "payments.balances.get" not in offered


def test_the_cards_agent_can_never_reach_the_money_door() -> None:
    agent = CardsAgent(chat=None, capabilities=_registry(), audit=_noop_audit)
    money = agent._capabilities.get("payments.transfer.propose")
    assert agent._may_call(money) is False


def test_the_card_action_is_declared_a_proposal_not_a_plain_read() -> None:
    assert "cards.action.propose" in PROPOSAL_TOOL_NAMES
    assert "cards.action.propose" not in TOOL_NAMES
