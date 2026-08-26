import pytest
from pydantic import BaseModel

from backend.agents.adapters import ChatResult, ToolCall
from backend.agents.analytics import AnalyticsAgent
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


async def test_agent_only_offers_its_own_capabilities_to_the_model() -> None:
    registry = _registry_with(
        ("analytics.cashflow_forecast.get", SideEffect.READ),
        ("analytics.goal_gap.get", SideEffect.READ),
        ("analytics.month_recap.get", SideEffect.READ),
        ("analytics.what_changed.get", SideEffect.READ),
        ("analytics.recommendations.get", SideEffect.READ),
        ("payments.transfer", SideEffect.MONEY_MOVING),
        ("settings.profile.get", SideEffect.READ),
    )
    chat = _ScriptedChat([ChatResult(content="hi", tool_calls=[], message={})])
    agent = AnalyticsAgent(chat=chat, capabilities=registry, audit=_noop_audit)
    actor = Actor(kind="agent", id="analytics-agent", on_behalf_of="user-1")

    await agent.ask(actor, "hello")

    offered = {tool["function"]["name"] for tool in chat.calls[0]["tools"]}
    assert offered == {
        "analytics.cashflow_forecast.get",
        "analytics.goal_gap.get",
        "analytics.month_recap.get",
        "analytics.what_changed.get",
        "analytics.recommendations.get",
    }


async def test_agent_refuses_a_tool_call_outside_its_allow_list() -> None:
    registry = _registry_with(
        ("analytics.month_recap.get", SideEffect.READ),
        ("payments.transfer", SideEffect.MONEY_MOVING),
    )
    chat = _ScriptedChat(
        [
            ChatResult(
                content=None,
                tool_calls=[ToolCall(id="1", name="payments.transfer", arguments="{}")],
                message={"role": "assistant"},
            )
        ]
    )
    agent = AnalyticsAgent(chat=chat, capabilities=registry, audit=_noop_audit)
    actor = Actor(kind="agent", id="analytics-agent", on_behalf_of="user-1")

    with pytest.raises(ValidationError):
        await agent.ask(actor, "move 100 RON to John")
