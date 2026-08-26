import pytest
from pydantic import BaseModel

from backend.agents.adapters import ChatResult, ToolCall
from backend.agents.base import MAX_TOOL_ROUNDS, ToolCallingAgent
from backend.capabilities.registry import Capability, CapabilityRegistry, SideEffect
from backend.helpers.context import Actor
from backend.helpers.errors import ValidationError


class _EmptyInput(BaseModel):
    pass


class _EchoOutput(BaseModel):
    value: str = "ok"


async def _resolver(actor: Actor, payload: BaseModel) -> BaseModel:
    return _EchoOutput()


def _registry_with(name: str, side_effect: SideEffect) -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register(
        Capability(
            name=name,
            input_schema=_EmptyInput,
            output_schema=_EchoOutput,
            side_effect=side_effect,
            required_scope="test",
            resolver=_resolver,
        )
    )
    return registry


class _ScriptedChat:
    def __init__(self, results: list[ChatResult]) -> None:
        self._results = list(results)

    async def complete(self, messages, tools):
        return self._results.pop(0)


class _RecordingAudit:
    def __init__(self) -> None:
        self.records: list[tuple[object, object, str]] = []

    async def __call__(self, record, actor, correlation_id) -> None:
        self.records.append((record, actor, correlation_id))


async def test_a_tool_call_and_the_final_answer_share_one_run_id_in_the_audit_trail() -> None:
    registry = _registry_with("demo.read", SideEffect.READ)
    chat = _ScriptedChat(
        [
            ChatResult(
                content=None,
                tool_calls=[ToolCall(id="1", name="demo.read", arguments="{}")],
                message={"role": "assistant"},
            ),
            ChatResult(content="here you go", tool_calls=[], message={}),
        ]
    )
    audit = _RecordingAudit()
    agent = ToolCallingAgent(
        name="demo",
        system_prompt="test",
        chat=chat,
        capabilities=registry,
        tool_names=frozenset({"demo.read"}),
        audit=audit,
    )
    actor = Actor(kind="agent", id="demo-agent", on_behalf_of="user-1")

    result = await agent.ask(actor, "question")

    assert result.answer == "here you go"
    assert result.capabilities_used == ["demo.read"]
    assert [record.action for record, _, _ in audit.records] == [
        "capability.demo.read",
        "agents.demo.answered",
    ]
    capability_record = audit.records[0][0]
    final_record = audit.records[1][0]
    assert capability_record.after["runId"] == final_record.entity_id
    assert audit.records[0][2] == audit.records[1][2]


async def test_agent_refuses_a_non_read_capability_even_if_it_is_allow_listed() -> None:
    registry = _registry_with("demo.write", SideEffect.WRITE)
    chat = _ScriptedChat(
        [
            ChatResult(
                content=None,
                tool_calls=[ToolCall(id="1", name="demo.write", arguments="{}")],
                message={"role": "assistant"},
            )
        ]
    )
    agent = ToolCallingAgent(
        name="demo",
        system_prompt="test",
        chat=chat,
        capabilities=registry,
        tool_names=frozenset({"demo.write"}),
        audit=_RecordingAudit(),
    )
    actor = Actor(kind="agent", id="demo-agent", on_behalf_of="user-1")

    with pytest.raises(ValidationError):
        await agent.ask(actor, "do something")


async def test_agent_gives_up_with_a_controlled_error_after_max_tool_rounds() -> None:
    registry = _registry_with("demo.read", SideEffect.READ)
    chat = _ScriptedChat(
        [
            ChatResult(
                content=None,
                tool_calls=[ToolCall(id=str(i), name="demo.read", arguments="{}")],
                message={"role": "assistant"},
            )
            for i in range(MAX_TOOL_ROUNDS)
        ]
    )
    agent = ToolCallingAgent(
        name="demo",
        system_prompt="test",
        chat=chat,
        capabilities=registry,
        tool_names=frozenset({"demo.read"}),
        audit=_RecordingAudit(),
    )
    actor = Actor(kind="agent", id="demo-agent", on_behalf_of="user-1")

    with pytest.raises(ValidationError):
        await agent.ask(actor, "question")
