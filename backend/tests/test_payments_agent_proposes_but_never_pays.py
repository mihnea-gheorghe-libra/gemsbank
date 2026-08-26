import asyncio
import json

import pytest
from pydantic import ValidationError as PydanticValidationError

from backend.agents.payments import PROPOSAL_TOOL_NAMES, TOOL_NAMES, PaymentsAgent
from backend.capabilities import payments as caps
from backend.capabilities.registry import Capability, CapabilityRegistry, SideEffect
from backend.helpers.context import Actor
from backend.helpers.errors import ValidationError

USER_ID = "user-1"
ACTOR = Actor(kind="agent", id="payments-agent", on_behalf_of=USER_ID)


def account(
    account_id: str,
    label: str,
    kind: str,
    currency: str,
    minor: int,
    iban: str,
    status: str = "active",
) -> dict:
    return {
        "accountId": account_id,
        "iban": iban,
        "ibanMasked": f"•• {iban[-4:]}",
        "holderName": "POPESCU ION",
        "currency": currency,
        "kind": kind,
        "label": label,
        "status": status,
        "balance": {"minorUnits": minor, "currency": currency},
    }


ACCOUNTS = [
    account("acc-ron-cur", "Current RON", "current", "RON", 250000, "RO49AAAA1B31007593840001"),
    account("acc-ron-sav", "Savings RON", "savings", "RON", 800000, "RO49AAAA1B31007593840002"),
    account("acc-eur-sav", "Savings EUR", "savings", "EUR", 120000, "RO49AAAA1B31007593840003"),
]


class FakeAccounts:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    async def list_for_user(self, user_id: str) -> list[dict]:
        assert user_id == USER_ID
        return self._rows

    async def resolve_iban(self, raw_iban: str):
        return None


class FakeLedger:
    def __init__(self, spent_today: int = 0) -> None:
        self.spent_today = spent_today
        self.posted: list[object] = []

    async def debited_since(self, account_ids: list[str], since) -> int:
        return self.spent_today

    async def post_transaction(self, *args, **kwargs):
        self.posted.append((args, kwargs))
        raise AssertionError("a proposal must never post to the ledger")


def balances(ref: str | None = None, rows: list[dict] | None = None):
    return asyncio.run(
        caps.resolve_balances(
            ACTOR,
            caps.BalancesInput(accountRef=ref),
            accounts_service=FakeAccounts(rows if rows is not None else ACCOUNTS),
        )
    )


def propose(ledger: FakeLedger | None = None, rows: list[dict] | None = None, **kwargs):
    payload = caps.TransferProposalInput(**kwargs)
    return asyncio.run(
        caps.resolve_transfer_proposal(
            ACTOR,
            payload,
            accounts_service=FakeAccounts(rows if rows is not None else ACCOUNTS),
            ledger_service=ledger or FakeLedger(),
        )
    )


def test_amounts_reach_the_model_preformatted_so_it_never_does_the_arithmetic() -> None:
    assert caps.format_minor(235000, "RON") == "2.350,00 RON"
    assert caps.format_minor(952, "EUR") == "9,52 EUR"
    assert caps.format_minor(0, "RON") == "0,00 RON"
    assert caps.format_minor(5, "RON") == "0,05 RON"
    assert caps.format_minor(-12345, "USD") == "-123,45 USD"
    assert caps.format_minor(123456789, "RON") == "1.234.567,89 RON"


def test_every_balance_carries_its_display_string() -> None:
    result = balances()
    assert [row.balance_formatted for row in result.accounts] == [
        "2.500,00 RON",
        "8.000,00 RON",
        "1.200,00 EUR",
    ]
    assert {row.currency: row.total_formatted for row in result.totals} == {
        "EUR": "1.200,00 EUR",
        "RON": "10.500,00 RON",
    }


def test_a_proposal_carries_display_strings_for_its_amount_and_what_is_left() -> None:
    result = propose(
        sourceAccountRef="current",
        targetAccountRef="savings ron",
        amountMinorUnits=50000,
        reference="Rent",
    )
    assert result.amount_formatted == "500,00 RON"
    assert result.balance_after_formatted == "2.000,00 RON"


def test_totals_are_reported_per_currency_and_never_summed_across_them() -> None:
    result = balances()
    assert result.status == "ok"
    assert len(result.accounts) == 3
    totals = {row.currency: row.total_minor for row in result.totals}
    assert totals == {"EUR": 120000, "RON": 1050000}


def test_naming_one_account_narrows_to_it_but_still_reports_every_total() -> None:
    result = balances("the euro account")
    assert result.status == "ok"
    assert [row.account_id for row in result.accounts] == ["acc-eur-sav"]
    assert {row.currency for row in result.totals} == {"EUR", "RON"}


def test_an_account_can_be_named_by_the_last_digits_of_its_iban() -> None:
    result = balances("the one ending 0002")
    assert result.status == "ok"
    assert [row.account_id for row in result.accounts] == ["acc-ron-sav"]


def test_a_currency_named_in_words_resolves_to_its_iso_code() -> None:
    for phrase in ("euro", "in euros", "my EUR savings"):
        result = balances(phrase)
        assert result.status == "ok", phrase
        assert [row.account_id for row in result.accounts] == ["acc-eur-sav"], phrase


def test_naming_both_a_kind_and_a_currency_pins_exactly_one_account() -> None:
    result = balances("ron savings")
    assert result.status == "ok"
    assert [row.account_id for row in result.accounts] == ["acc-ron-sav"]


def test_a_kind_and_currency_pair_that_matches_nothing_does_not_fall_back() -> None:
    result = balances("usd current")
    assert result.status == "no_match"


def test_an_ambiguous_account_name_asks_instead_of_guessing() -> None:
    result = balances("savings")
    assert result.status == "ambiguous"
    assert {row.account_id for row in result.candidates} == {"acc-ron-sav", "acc-eur-sav"}
    assert result.accounts == []


def test_an_unrecognised_account_name_offers_candidates_rather_than_a_number() -> None:
    result = balances("my mortgage")
    assert result.status == "no_match"
    assert result.accounts == []
    assert len(result.candidates) == 3


def test_a_customer_with_no_accounts_gets_no_accounts_not_a_zero() -> None:
    result = balances(rows=[])
    assert result.status == "no_accounts"
    assert result.totals == []


def test_a_clean_proposal_never_reaches_the_ledger() -> None:
    ledger = FakeLedger()
    result = propose(
        ledger=ledger,
        sourceAccountRef="current",
        targetAccountRef="savings ron",
        amountMinorUnits=50000,
        reference="Rent",
    )
    assert result.status == "proposed"
    assert result.requires_human_confirmation is True
    assert result.auto_approval_eligible is False
    assert result.balance_after_minor == 200000
    assert ledger.posted == []


def test_a_proposal_above_the_step_up_threshold_says_it_needs_a_signature() -> None:
    result = propose(
        sourceAccountRef="savings ron",
        targetAccountRef="current",
        amountMinorUnits=150000,
        reference="Big one",
    )
    assert result.status == "proposed"
    assert result.requires_signature is True


def test_a_proposal_beyond_the_balance_is_blocked_with_no_amount_invented() -> None:
    result = propose(
        sourceAccountRef="current",
        targetAccountRef="savings ron",
        amountMinorUnits=9_000_00,
        reference="Too much",
    )
    assert result.status == "blocked"
    assert "insufficient_funds" in {blocker.code for blocker in result.blockers}


def test_a_cross_currency_proposal_is_blocked_because_payments_do_not_convert() -> None:
    result = propose(
        sourceAccountRef="current",
        targetAccountRef="euro",
        amountMinorUnits=10000,
        reference="Holiday",
    )
    assert result.status == "blocked"
    assert "currency_mismatch" in {blocker.code for blocker in result.blockers}


def test_a_proposal_over_the_per_transaction_limit_is_blocked_by_the_policy_engine() -> None:
    rows = [account("acc-rich", "Current RON", "current", "RON", 99_999_999, "RO49AAAA1B31007593840009")]
    result = propose(
        rows=rows + [account("acc-t", "Savings RON", "savings", "RON", 0, "RO49AAAA1B31007593840010")],
        sourceAccountRef="current",
        targetAccountRef="savings",
        amountMinorUnits=50_000_00,
        reference="Over limit",
    )
    assert result.status == "blocked"
    assert "over_per_transaction_limit" in {blocker.code for blocker in result.blockers}


def test_the_daily_limit_counts_what_was_already_spent_today() -> None:
    rows = [
        account("acc-a", "Current RON", "current", "RON", 99_999_999, "RO49AAAA1B31007593840011"),
        account("acc-b", "Savings RON", "savings", "RON", 0, "RO49AAAA1B31007593840012"),
    ]
    result = propose(
        rows=rows,
        ledger=FakeLedger(spent_today=49_000_00),
        sourceAccountRef="current",
        targetAccountRef="savings",
        amountMinorUnits=19_000_00,
        reference="Tips the daily limit",
    )
    assert result.status == "blocked"
    assert "over_daily_limit" in {blocker.code for blocker in result.blockers}


def test_an_iban_that_is_not_held_at_gems_is_refused_not_routed_externally() -> None:
    result = propose(
        sourceAccountRef="current",
        targetIban="RO49BBBB1B31007593849999",
        counterparty="Someone Else",
        amountMinorUnits=1000,
        reference="External",
    )
    assert result.status == "blocked"
    assert "iban_unreachable" in {blocker.code for blocker in result.blockers}


def test_an_ambiguous_source_account_asks_instead_of_picking_one() -> None:
    result = propose(
        sourceAccountRef="savings",
        targetAccountRef="current",
        amountMinorUnits=1000,
        reference="Which savings?",
    )
    assert result.status == "needs_clarification"
    assert "source_ambiguous" in {blocker.code for blocker in result.blockers}
    assert len(result.candidates) == 2


def test_a_payment_to_an_iban_without_a_payee_name_asks_for_one() -> None:
    result = propose(
        sourceAccountRef="current",
        targetIban="RO49AAAA1B31007593840002",
        amountMinorUnits=1000,
        reference="No name",
    )
    assert result.status in {"needs_clarification", "blocked"}


def test_a_negative_or_zero_amount_never_reaches_the_resolver() -> None:
    for amount in (0, -1, -50000):
        with pytest.raises(PydanticValidationError):
            caps.TransferProposalInput(
                sourceAccountRef="current",
                targetAccountRef="savings",
                amountMinorUnits=amount,
                reference="Not a real amount",
            )


class RecordingChat:
    def __init__(self, script: list) -> None:
        self._script = list(script)
        self.tools_offered: list[list[dict]] = []
        self.transcripts: list[list[dict]] = []

    async def complete(self, messages, tools):
        self.tools_offered.append(tools)
        self.transcripts.append([dict(message) for message in messages])
        return self._script.pop(0)


def registry_with_a_write_capability() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register(
        Capability(
            name="payments.balances.get",
            input_schema=caps.BalancesInput,
            output_schema=caps.BalancesOutput,
            side_effect=SideEffect.READ,
            required_scope="accounts:read",
            resolver=lambda actor, payload: _never_called(),
        )
    )
    registry.register(
        Capability(
            name="payments.transfer.propose",
            input_schema=caps.TransferProposalInput,
            output_schema=caps.TransferProposalOutput,
            side_effect=SideEffect.MONEY_MOVING,
            required_scope="payments:propose",
            resolver=lambda actor, payload: _never_called(),
        )
    )
    registry.register(
        Capability(
            name="payments.transfer.execute",
            input_schema=caps.TransferProposalInput,
            output_schema=caps.TransferProposalOutput,
            side_effect=SideEffect.WRITE,
            required_scope="payments:write",
            resolver=lambda actor, payload: _never_called(),
        )
    )
    return registry


async def _never_called():
    raise AssertionError("this capability must not be reachable")


async def _noop_audit(record, actor, correlation_id) -> None:
    return None


def test_the_payments_agent_is_offered_its_reads_and_its_proposal_and_nothing_else() -> None:
    registry = registry_with_a_write_capability()
    chat = RecordingChat([])
    agent = PaymentsAgent(chat=chat, capabilities=registry, audit=_noop_audit)
    offered = {tool["function"]["name"] for tool in agent._tool_defs()}
    assert offered == {"payments.balances.get", "payments.transfer.propose"}
    assert "payments.transfer.execute" not in offered


def _asked_for(name: str, then: str = "done"):
    from backend.agents.adapters import ChatResult, ToolCall

    return [
        ChatResult(
            content=None,
            tool_calls=[ToolCall(id="1", name=name, arguments="{}")],
            message={"role": "assistant"},
        ),
        ChatResult(content=then, message={"role": "assistant", "content": then}),
    ]


def test_a_registered_write_capability_outside_the_grant_fails_loudly() -> None:
    registry = registry_with_a_write_capability()
    chat = RecordingChat(_asked_for("payments.transfer.execute"))
    agent = PaymentsAgent(chat=chat, capabilities=registry, audit=_noop_audit)

    with pytest.raises(ValidationError):
        asyncio.run(agent.ask(ACTOR, "just send it"))


def test_a_misspelled_capability_is_corrected_in_loop_rather_than_crashing() -> None:
    registry = registry_with_a_write_capability()
    chat = RecordingChat(_asked_for("transfer.propose"))
    agent = PaymentsAgent(chat=chat, capabilities=registry, audit=_noop_audit)

    answer = asyncio.run(agent.ask(ACTOR, "send it"))

    tool_reply = json.loads(chat.transcripts[-1][-1]["content"])
    assert tool_reply["error"] == "no_such_capability"
    assert "payments.transfer.propose" in tool_reply["message"]
    assert answer.capabilities_used == []
    assert answer.proposals == []


def test_a_run_that_never_settles_still_fails_loudly() -> None:
    from backend.agents.adapters import ChatResult, ToolCall

    registry = registry_with_a_write_capability()
    chat = RecordingChat(
        [
            ChatResult(
                content=None,
                tool_calls=[ToolCall(id=str(i), name="nope.nope", arguments="{}")],
                message={"role": "assistant"},
            )
            for i in range(8)
        ]
    )
    agent = PaymentsAgent(chat=chat, capabilities=registry, audit=_noop_audit)
    with pytest.raises(ValidationError):
        asyncio.run(agent.ask(ACTOR, "loop forever"))


def test_the_support_agent_cannot_reach_a_money_moving_capability() -> None:
    from backend.agents.support import SupportAgent

    registry = registry_with_a_write_capability()
    agent = SupportAgent(chat=RecordingChat([]), capabilities=registry, audit=_noop_audit)
    offered = {tool["function"]["name"] for tool in agent._tool_defs()}
    assert "payments.transfer.propose" not in offered
    assert agent.proposal_tool_names == frozenset()


def test_the_analytics_agent_cannot_reach_a_money_moving_capability() -> None:
    from backend.agents.analytics import AnalyticsAgent

    registry = registry_with_a_write_capability()
    agent = AnalyticsAgent(chat=RecordingChat([]), capabilities=registry, audit=_noop_audit)
    offered = {tool["function"]["name"] for tool in agent._tool_defs()}
    assert "payments.transfer.propose" not in offered
    assert agent.proposal_tool_names == frozenset()


def test_the_proposal_capability_is_declared_money_moving_in_the_registry() -> None:
    assert "payments.transfer.propose" in PROPOSAL_TOOL_NAMES
    assert "payments.transfer.propose" not in TOOL_NAMES
