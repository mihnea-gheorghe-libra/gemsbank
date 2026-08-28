import pytest
from pydantic import BaseModel

from backend.agents.adapters import ChatResult, ToolCall
from backend.agents.education import PROPOSAL_TOOL_NAMES, TOOL_NAMES, EducationAgent
from backend.capabilities.registry import Capability, CapabilityRegistry, SideEffect
from backend.helpers.context import Actor
from backend.helpers.errors import ValidationError


class _EmptyInput(BaseModel):
    pass


class _EmptyOutput(BaseModel):
    ok: bool = True


async def _noop_resolver(actor: Actor, payload: BaseModel) -> BaseModel:
    return _EmptyOutput()


def _registry_with(*entries: tuple[str, SideEffect]) -> CapabilityRegistry:
    registry = CapabilityRegistry()
    for name, side_effect in entries:
        registry.register(
            Capability(
                name=name,
                input_schema=_EmptyInput,
                output_schema=_EmptyOutput,
                side_effect=side_effect,
                required_scope="test",
                resolver=_noop_resolver,
            )
        )
    return registry


class _ScriptedChat:
    def __init__(self, results: list[ChatResult]) -> None:
        self._results = list(results)
        self.calls: list[dict[str, object]] = []

    async def complete(self, messages, tools):
        self.calls.append({"messages": messages, "tools": tools})
        return self._results.pop(0)


async def _noop_audit(record, actor, correlation_id) -> None:
    return None


def _full_registry() -> CapabilityRegistry:
    return _registry_with(
        ("education.docs.search", SideEffect.READ),
        ("analytics.goal_gap.get", SideEffect.READ),
        ("analytics.cashflow_forecast.get", SideEffect.READ),
        ("payments.balances.get", SideEffect.READ),
        ("goals.create.propose", SideEffect.WRITE),
        ("payments.transfer.propose", SideEffect.MONEY_MOVING),
    )


async def test_agent_offers_its_reads_and_its_write_proposal_and_nothing_else() -> None:
    registry = _full_registry()
    chat = _ScriptedChat([ChatResult(content="hi", tool_calls=[], message={})])
    agent = EducationAgent(chat=chat, capabilities=registry, audit=_noop_audit)
    actor = Actor(kind="agent", id="education-agent", on_behalf_of="user-1")

    await agent.ask(actor, "hello")

    offered = {tool["function"]["name"] for tool in chat.calls[0]["tools"]}
    assert offered == {
        "education.docs.search",
        "analytics.goal_gap.get",
        "analytics.cashflow_forecast.get",
        "payments.balances.get",
        "goals.create.propose",
    }
    assert "payments.transfer.propose" not in offered


async def test_agent_never_reaches_a_money_moving_capability() -> None:
    registry = _full_registry()
    chat = _ScriptedChat(
        [
            ChatResult(
                content=None,
                tool_calls=[ToolCall(id="1", name="payments.transfer.propose", arguments="{}")],
                message={"role": "assistant"},
            )
        ]
    )
    agent = EducationAgent(chat=chat, capabilities=registry, audit=_noop_audit)
    actor = Actor(kind="agent", id="education-agent", on_behalf_of="user-1")

    with pytest.raises(ValidationError):
        await agent.ask(actor, "move money instead")


def test_the_goal_proposal_capability_is_declared_write_not_money_moving() -> None:
    assert "goals.create.propose" in PROPOSAL_TOOL_NAMES
    assert "goals.create.propose" not in TOOL_NAMES
