import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from backend.agents.adapters import ChatCompleter
from backend.capabilities.registry import CapabilityRegistry, SideEffect
from backend.database.records import AuditRecord
from backend.helpers.context import Actor, get_correlation_id, log_event, new_id
from backend.helpers.errors import ValidationError

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 4

AuditSink = Callable[[AuditRecord, Actor, str], Awaitable[None]]


@dataclass(slots=True)
class AgentAnswer:
    answer: str
    capabilities_used: list[str] = field(default_factory=list)


class ToolCallingAgent:
    def __init__(
        self,
        name: str,
        system_prompt: str,
        chat: ChatCompleter,
        capabilities: CapabilityRegistry,
        tool_names: frozenset[str],
        audit: AuditSink,
    ) -> None:
        self._name = name
        self._system_prompt = system_prompt
        self._chat = chat
        self._capabilities = capabilities
        self._tool_names = tool_names
        self._audit = audit

    @property
    def tool_names(self) -> frozenset[str]:
        return self._tool_names

    def _tool_defs(self) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": capability.name,
                    "description": capability.name,
                    "parameters": capability.input_schema.model_json_schema(),
                },
            }
            for capability in self._capabilities.all()
            if capability.name in self._tool_names and capability.side_effect is SideEffect.READ
        ]

    async def ask(self, actor: Actor, question: str) -> AgentAnswer:
        run_id = new_id()
        correlation_id = get_correlation_id()
        messages: list[dict[str, object]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": question},
        ]
        tools = self._tool_defs()
        used: list[str] = []

        for _ in range(MAX_TOOL_ROUNDS):
            result = await self._chat.complete(messages, tools)
            if not result.tool_calls:
                await self._audit(
                    AuditRecord(
                        action=f"agents.{self._name}.answered",
                        entity_type="agent_run",
                        entity_id=run_id,
                        after={
                            "subject": actor.subject_id(),
                            "question": question,
                            "answer": result.content or "",
                            "capabilitiesUsed": used,
                        },
                    ),
                    actor,
                    correlation_id,
                )
                log_event(
                    logger,
                    f"agents.{self._name}.answered",
                    actor=actor.label(),
                    subject=actor.subject_id(),
                    runId=run_id,
                    capabilities=used,
                )
                return AgentAnswer(answer=result.content or "", capabilities_used=used)

            messages.append(result.message)
            for call in result.tool_calls:
                if call.name not in self._tool_names:
                    raise ValidationError(
                        f"{self._name} may not call that capability.",
                        details={"capability": call.name},
                    )
                capability = self._capabilities.get(call.name)
                if capability.side_effect is not SideEffect.READ:
                    raise ValidationError(
                        f"{self._name} may only call read-only capabilities.",
                        details={"capability": capability.name},
                    )
                arguments = json.loads(call.arguments or "{}")
                payload = capability.input_schema.model_validate(arguments)
                output = await capability.resolve(actor, payload)
                used.append(capability.name)
                await self._audit(
                    AuditRecord(
                        action=f"capability.{capability.name}",
                        entity_type="capability",
                        entity_id=capability.name,
                        after={"subject": actor.subject_id(), "runId": run_id},
                    ),
                    actor,
                    correlation_id,
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": output.model_dump_json(by_alias=True),
                    }
                )

        raise ValidationError(f"{self._name} could not settle on an answer in time.")
