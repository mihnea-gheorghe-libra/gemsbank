import pytest
from pydantic import BaseModel

from backend.capabilities.registry import Capability, CapabilityRegistry, SideEffect
from backend.helpers.context import Actor
from backend.helpers.errors import NotFoundError


class _EmptyInput(BaseModel):
    pass


class _EchoOutput(BaseModel):
    seen: str


async def _resolver(actor: Actor, payload: BaseModel) -> BaseModel:
    return _EchoOutput(seen=actor.subject_id())


def _capability(name: str, side_effect: SideEffect = SideEffect.READ) -> Capability:
    return Capability(
        name=name,
        input_schema=_EmptyInput,
        output_schema=_EchoOutput,
        side_effect=side_effect,
        required_scope="test:read",
        resolver=_resolver,
    )


def test_all_returns_registered_capabilities_sorted_by_name() -> None:
    registry = CapabilityRegistry()
    registry.register(_capability("b.one"))
    registry.register(_capability("a.two"))
    assert [c.name for c in registry.all()] == ["a.two", "b.one"]


def test_register_rejects_a_duplicate_name() -> None:
    registry = CapabilityRegistry()
    registry.register(_capability("dup"))
    with pytest.raises(ValueError):
        registry.register(_capability("dup"))


def test_get_raises_not_found_for_an_unknown_capability() -> None:
    registry = CapabilityRegistry()
    with pytest.raises(NotFoundError):
        registry.get("does.not.exist")


async def test_resolve_calls_the_resolver_with_the_calling_actor() -> None:
    registry = CapabilityRegistry()
    registry.register(_capability("echo"))
    capability = registry.get("echo")
    actor = Actor(kind="agent", id="support-agent", on_behalf_of="user-1")

    output = await capability.resolve(actor, _EmptyInput())

    assert isinstance(output, _EchoOutput)
    assert output.seen == "user-1"


async def test_support_faq_search_is_registered_and_resolves() -> None:
    from backend.capabilities.service import get_capabilities_service

    capability = get_capabilities_service().get("support.faq.search")
    actor = Actor(kind="agent", id="support-agent", on_behalf_of="user-1")
    payload = capability.input_schema(query="card")

    output = await capability.resolve(actor, payload)

    assert output.results
