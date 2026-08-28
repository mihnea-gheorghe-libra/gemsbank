from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from backend.helpers.context import Actor
from backend.helpers.errors import NotFoundError
from pydantic import BaseModel


class SideEffect(StrEnum):
    READ = "read"
    WRITE = "write"
    MONEY_MOVING = "money-moving"


Resolver = Callable[[Actor, BaseModel], Awaitable[BaseModel]]


@dataclass(slots=True, frozen=True)
class Capability:
    name: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    side_effect: SideEffect
    required_scope: str
    resolver: Resolver

    async def resolve(self, actor: Actor, payload: BaseModel) -> BaseModel:
        return await self.resolver(actor, payload)

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sideEffect": self.side_effect.value,
            "requiredScope": self.required_scope,
            "inputSchema": self.input_schema.model_json_schema(),
            "outputSchema": self.output_schema.model_json_schema(),
        }


class CapabilityRegistry:
    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}

    def register(self, capability: Capability) -> None:
        if capability.name in self._capabilities:
            raise ValueError(f"Capability '{capability.name}' is already registered.")
        self._capabilities[capability.name] = capability

    def get(self, name: str) -> Capability:
        capability = self._capabilities.get(name)
        if capability is None:
            raise NotFoundError(f"No capability named '{name}'.", details={"name": name})
        return capability

    def all(self) -> list[Capability]:
        return [self._capabilities[name] for name in sorted(self._capabilities)]


registry = CapabilityRegistry()
