import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.agents.education import PROPOSAL_TOOL_NAMES, TOOL_NAMES, EducationAgent
from backend.capabilities import education as edu_caps
from backend.capabilities.registry import Capability, CapabilityRegistry, SideEffect
from backend.helpers.context import Actor

USER_ID = "user-1"
ACTOR = Actor(kind="agent", id="education-agent", on_behalf_of=USER_ID)


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
    account("acc-ron-cur", "Everyday Checking", "current", "RON", 250000, "RO49AAAA1B31007593840001"),
    account("acc-ron-sav", "High-Yield Savings", "savings", "RON", 800000, "RO49AAAA1B31007593840002"),
    account("acc-eur-sav", "EUR Savings", "savings", "EUR", 120000, "RO49AAAA1B31007593840003"),
]


class FakeAccounts:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    async def list_for_user(self, user_id: str) -> list[dict]:
        assert user_id == USER_ID
        return self._rows


class FakeGoals:
    def __init__(self, active: list[object] | None = None) -> None:
        self.active = active or []

    async def list_active_for_user(self, user_id: str):
        return self.active


async def _noop_audit(record, actor, correlation_id) -> None:
    return None


def test_education_agent_sees_only_assigned_tools_and_proposals() -> None:
    registry = CapabilityRegistry()
    for name in sorted(TOOL_NAMES):
        registry.register(
            Capability(
                name=name,
                input_schema=edu_caps.EducationSearchInput,
                output_schema=edu_caps.EducationSearchOutput,
                side_effect=SideEffect.READ,
                required_scope="test",
                resolver=lambda a, p: None,
            )
        )
    for name in ("goals.create.propose", "goals.standingOrder.propose"):
        registry.register(
            Capability(
                name=name,
                input_schema=edu_caps.GoalProposalInput,
                output_schema=edu_caps.GoalProposalOutput,
                side_effect=SideEffect.WRITE,
                required_scope="test",
                resolver=lambda a, p: None,
            )
        )
    registry.register(
        Capability(
            name="payments.transfer.propose",
            input_schema=edu_caps.GoalProposalInput,
            output_schema=edu_caps.GoalProposalOutput,
            side_effect=SideEffect.MONEY_MOVING,
            required_scope="test",
            resolver=lambda a, p: None,
        )
    )

    agent = EducationAgent(chat=None, capabilities=registry, audit=_noop_audit)
    offered = {t["function"]["name"] for t in agent._tool_defs()}
    assert offered == (TOOL_NAMES | PROPOSAL_TOOL_NAMES)
    assert "payments.transfer.propose" not in offered


def test_goal_proposal_calculates_pacing_and_formatted_rates() -> None:
    target_date = datetime.now(timezone.utc).date() + timedelta(days=90)
    result = asyncio.run(
        edu_caps.resolve_goal_proposal(
            ACTOR,
            edu_caps.GoalProposalInput(
                accountRef="contul curent",
                name="Geantă",
                targetMinorUnits=500000,
                targetDate=target_date,
            ),
            accounts_service=FakeAccounts(ACCOUNTS),
            goals_service=FakeGoals(),
        )
    )
    assert isinstance(result, edu_caps.GoalProposalOutput)
    assert result.status == "proposed"
    assert result.name == "Geantă"
    assert result.target_formatted == "5.000,00 RON"
    assert result.account_label == "Everyday Checking"
    assert result.days_remaining == 90
    assert result.weeks_remaining == 13
    assert result.months_remaining == 3
    assert result.suggested_monthly_formatted is not None
    assert "RON" in result.suggested_monthly_formatted
    assert result.suggested_weekly_formatted is not None
    assert "RON" in result.suggested_weekly_formatted


@pytest.mark.parametrize(
    "ref",
    ["curent", "cont curent", "contul curent", "contul principal", "Everyday", "Checking"],
)
def test_goal_proposal_resolves_romanian_account_references(ref: str) -> None:
    target_date = datetime.now(timezone.utc).date() + timedelta(days=60)
    result = asyncio.run(
        edu_caps.resolve_goal_proposal(
            ACTOR,
            edu_caps.GoalProposalInput(
                accountRef=ref,
                name="Economii",
                targetMinorUnits=100000,
                targetDate=target_date,
            ),
            accounts_service=FakeAccounts(ACCOUNTS),
            goals_service=FakeGoals(),
        )
    )
    assert isinstance(result, edu_caps.GoalProposalOutput)
    assert result.status == "proposed"
    assert result.account_id == "acc-ron-cur"


def test_goal_proposal_asks_clarification_when_multiple_accounts_match_currency() -> None:
    target_date = datetime.now(timezone.utc).date() + timedelta(days=60)
    result = asyncio.run(
        edu_caps.resolve_goal_proposal(
            ACTOR,
            edu_caps.GoalProposalInput(
                accountRef="RON",
                name="Economii",
                targetMinorUnits=100000,
                targetDate=target_date,
            ),
            accounts_service=FakeAccounts(ACCOUNTS),
            goals_service=FakeGoals(),
        )
    )
    assert isinstance(result, edu_caps.GoalProposalOutput)
    assert result.status == "needs_clarification"
    assert any(b.code == "account_ambiguous" for b in result.blockers)


LOOKALIKE_ACCOUNTS = [
    account("acc-ron-cur", "Cont curent", "current", "RON", 35000, "RO49AAAA1B31007593840163"),
    account("acc-usd-cur", "Cont curent USD", "current", "USD", 4429, "RO49AAAA1B31007593848214"),
]


def _lookalike_proposal(**extra) -> edu_caps.GoalProposalOutput:
    target_date = datetime.now(timezone.utc).date() + timedelta(days=120)
    result = asyncio.run(
        edu_caps.resolve_goal_proposal(
            ACTOR,
            edu_caps.GoalProposalInput(
                accountRef="curent",
                name="Geantă",
                targetMinorUnits=500000,
                targetDate=target_date,
                **extra,
            ),
            accounts_service=FakeAccounts(LOOKALIKE_ACCOUNTS),
            goals_service=FakeGoals(),
        )
    )
    assert isinstance(result, edu_caps.GoalProposalOutput)
    return result


def test_goal_proposal_still_asks_which_account_when_no_currency_is_named() -> None:
    result = _lookalike_proposal()

    assert result.status == "needs_clarification"
    assert any(b.code == "account_ambiguous" for b in result.blockers)


def test_the_named_currency_settles_two_accounts_answering_to_the_same_words() -> None:
    result = _lookalike_proposal(currency="RON")

    assert result.status == "proposed"
    assert result.account_id == "acc-ron-cur"
    assert result.currency == "RON"
    assert result.target_formatted == "5.000,00 RON"


def test_a_currency_none_of_the_matches_hold_does_not_pick_one_at_random() -> None:
    result = _lookalike_proposal(currency="EUR")

    assert result.status == "needs_clarification"
    assert any(b.code == "account_ambiguous" for b in result.blockers)


def test_goal_proposal_blocks_duplicate_goal_names() -> None:
    class FakeGoalObj:
        name = "Geantă"

    target_date = datetime.now(timezone.utc).date() + timedelta(days=60)
    result = asyncio.run(
        edu_caps.resolve_goal_proposal(
            ACTOR,
            edu_caps.GoalProposalInput(
                accountRef="curent",
                name="geantă",
                targetMinorUnits=100000,
                targetDate=target_date,
            ),
            accounts_service=FakeAccounts(ACCOUNTS),
            goals_service=FakeGoals([FakeGoalObj()]),
        )
    )
    assert isinstance(result, edu_caps.GoalProposalOutput)
    assert result.status == "blocked"
    assert any(b.code == "duplicate_goal_name" for b in result.blockers)


class _ScriptedChat:
    def __init__(self, results: list) -> None:
        self._results = list(results)

    async def complete(self, messages, tools):
        return self._results.pop(0)


def test_education_agent_proposes_goal_and_returns_pacing_options() -> None:
    from backend.agents.adapters import ChatResult, ToolCall
    import json

    registry = CapabilityRegistry()
    registry.register(
        Capability(
            name="goals.create.propose",
            input_schema=edu_caps.GoalProposalInput,
            output_schema=edu_caps.GoalProposalOutput,
            side_effect=SideEffect.WRITE,
            required_scope="goals:propose",
            resolver=lambda a, p: edu_caps.resolve_goal_proposal(
                a, p, accounts_service=FakeAccounts(ACCOUNTS), goals_service=FakeGoals()
            ),
        )
    )

    chat = _ScriptedChat(
        [
            ChatResult(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        name="goals.create.propose",
                        arguments=json.dumps(
                            {
                                "accountRef": "contul curent",
                                "name": "Geantă",
                                "targetMinorUnits": 500000,
                                "targetDate": "2026-12-01",
                            }
                        ),
                    )
                ],
                message={"role": "assistant"},
            ),
            ChatResult(
                content=(
                    "Am pregătit obiectivul **Geantă** pentru **5.000,00 RON** din contul tău "
                    "**Everyday Checking** până la **01.12.2026**.\n\n"
                    "Iată opțiunile de economisire:\n"
                    "- **1.666,67 RON / lună**\n"
                    "- **384,62 RON / săptămână**\n\n"
                    "Recomandarea mea este să alegi varianta lunară imediat după salariu."
                ),
                tool_calls=[],
                message={},
            ),
        ]
    )

    agent = EducationAgent(chat=chat, capabilities=registry, audit=_noop_audit)
    answer = asyncio.run(
        agent.ask(
            ACTOR,
            "fa mi un obiectiv in care sa economisesc 5000 lei pentru o geanta pana la 1 dec 2026",
        )
    )

    assert len(answer.proposals) == 1
    proposal = answer.proposals[0]
    assert proposal["status"] == "proposed"
    assert proposal["name"] == "Geantă"
    assert proposal["targetFormatted"] == "5.000,00 RON"
    assert proposal["suggestedMonthlyFormatted"] is not None
    assert proposal["suggestedWeeklyFormatted"] is not None
    assert "Geantă" in answer.answer
    assert "1.666,67 RON" in answer.answer


def test_orchestrator_routes_savings_goal_question_to_education() -> None:
    from backend.agents.adapters import ChatResult, ToolCall
    from backend.agents.orchestrator import Orchestrator
    import json

    class _MockEducationWorker:
        async def ask(self, actor, question, history=None, run_id=None):
            return edu_caps.GoalProposalOutput(
                status="proposed",
                proposalId="goal-123",
                name="Geantă",
                targetFormatted="5.000,00 RON",
            )

    class _EducationProposingAgent:
        async def ask(self, actor, question, history=None, run_id=None):
            from backend.agents.base import AgentAnswer
            return AgentAnswer(
                answer="Am pregătit obiectivul **Geantă** pentru confirmare.",
                capabilities_used=["goals.create.propose"],
                proposals=[
                    {
                        "status": "proposed",
                        "proposalKind": "goal",
                        "name": "Geantă",
                        "targetFormatted": "5.000,00 RON",
                    }
                ],
            )

    chat = _ScriptedChat(
        [
            ChatResult(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call-orch",
                        name="ask_education",
                        arguments=json.dumps(
                            {
                                "question": "fa mi un obiectiv in care sa economisesc 5000 lei pentru o geanta pana la 1 dec 2026",
                            }
                        ),
                    )
                ],
                message={"role": "assistant"},
            )
        ]
    )

    orchestrator = Orchestrator(
        chat=chat,
        workers={"education": _EducationProposingAgent()},
        audit=_noop_audit,
    )

    result = asyncio.run(
        orchestrator.ask(
            ACTOR,
            "fa mi un obiectiv in care sa economisesc 5000 lei pentru o geanta pana la 1 dec 2026",
            screen="education",
        )
    )

    assert result.agents_used == ["education"]
    assert len(result.proposals) == 1
    assert result.proposals[0]["proposalKind"] == "goal"
    assert result.proposals[0]["name"] == "Geantă"
    assert "Geantă" in result.answer
