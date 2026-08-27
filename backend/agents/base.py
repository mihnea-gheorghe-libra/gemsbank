import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pydantic import ValidationError as PydanticValidationError

from backend.agents.adapters import ChatCompleter
from backend.capabilities.registry import Capability, CapabilityRegistry, SideEffect
from backend.database.records import AuditRecord
from backend.helpers.context import Actor, get_correlation_id, log_event, new_id
from backend.helpers.errors import NotFoundError, ValidationError

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 4

AuditSink = Callable[[AuditRecord, Actor, str], Awaitable[None]]


@dataclass(slots=True)
class AgentAnswer:
    answer: str
    capabilities_used: list[str] = field(default_factory=list)
    proposals: list[dict[str, object]] = field(default_factory=list)


class ToolCallingAgent:
    def __init__(
        self,
        name: str,
        system_prompt: str,
        chat: ChatCompleter,
        capabilities: CapabilityRegistry,
        tool_names: frozenset[str],
        audit: AuditSink,
        proposal_tool_names: frozenset[str] = frozenset(),
    ) -> None:
        self._name = name
        self._system_prompt = system_prompt
        self._chat = chat
        self._capabilities = capabilities
        self._tool_names = tool_names
        self._proposal_tool_names = proposal_tool_names
        self._audit = audit

    @property
    def tool_names(self) -> frozenset[str]:
        return self._tool_names

    @property
    def proposal_tool_names(self) -> frozenset[str]:
        return self._proposal_tool_names

    def _may_call(self, capability: Capability) -> bool:
        if capability.name in self._tool_names:
            return capability.side_effect is SideEffect.READ
        if capability.name in self._proposal_tool_names:
<<<<<<< HEAD
            return capability.side_effect in (SideEffect.MONEY_MOVING, SideEffect.WRITE)
=======
            return capability.side_effect in (SideEffect.WRITE, SideEffect.MONEY_MOVING)
>>>>>>> f246952780604fd79494ff16c6ba4db93b0d52b8
        return False

    def _granted_capability(self, name: str) -> Capability | None:
        try:
            capability = self._capabilities.get(name)
        except NotFoundError:
            return None
        if not self._may_call(capability):
            raise ValidationError(
                f"{self._name} may not call that capability.",
                details={"capability": name},
            )
        return capability

    def _tool_error(self, call_id: str, code: str, message: str) -> dict[str, object]:
        return {
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps({"error": code, "message": message}),
        }

    def _unknown_capability(self, call_id: str, requested: str) -> dict[str, object]:
        allowed = sorted(self._tool_names | self._proposal_tool_names)
        return self._tool_error(
            call_id,
            "no_such_capability",
            f"There is no capability called '{requested}'. "
            f"The exact names available are: {', '.join(allowed)}.",
        )

    def _tool_defs(self) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": capability.name,
                    "description": f"Call this tool using exactly this name: '{capability.name}'.",
                    "parameters": capability.input_schema.model_json_schema(),
                },
            }
            for capability in self._capabilities.all()
            if self._may_call(capability)
        ]

    async def ask(
        self,
        actor: Actor,
        question: str,
        history: list[dict[str, str]] | None = None,
        run_id: str | None = None,
    ) -> AgentAnswer:
        run_id = run_id or new_id()
        correlation_id = get_correlation_id()
        prior: list[dict[str, object]] = [
            {"role": turn["role"], "content": turn["content"]} for turn in history or []
        ]
        messages: list[dict[str, object]] = [
            {"role": "system", "content": self._system_prompt},
            *prior,
            {"role": "user", "content": question},
        ]
        tools = self._tool_defs()
        used: list[str] = []
        proposals: list[dict[str, object]] = []

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
                            "proposals": proposals,
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
                    proposals=len(proposals),
                )
                return AgentAnswer(
                    answer=result.content or "",
                    capabilities_used=used,
                    proposals=proposals,
                )

            messages.append(result.message)
            for call in result.tool_calls:
                capability = self._granted_capability(call.name)
                if capability is None:
                    log_event(
                        logger,
                        f"agents.{self._name}.unknown_capability",
                        actor=actor.label(),
                        runId=run_id,
                        requested=call.name,
                    )
                    messages.append(self._unknown_capability(call.id, call.name))
                    continue
                try:
                    arguments = json.loads(call.arguments or "{}")
                    payload = capability.input_schema.model_validate(arguments)
                except (json.JSONDecodeError, PydanticValidationError) as exc:
                    log_event(
                        logger,
                        f"agents.{self._name}.capability_arguments_rejected",
                        actor=actor.label(),
                        runId=run_id,
                        requested=call.name,
                    )
                    messages.append(
                        self._tool_error(
                            call.id,
                            "invalid_arguments",
                            f"Those arguments do not fit {call.name}: {exc}",
                        )
                    )
                    continue
                output = await capability.resolve(actor, payload)
                used.append(capability.name)
<<<<<<< HEAD
                is_proposal = capability.side_effect in (
                    SideEffect.MONEY_MOVING,
                    SideEffect.WRITE,
                )
=======
                is_proposal = capability.name in self._proposal_tool_names
>>>>>>> f246952780604fd79494ff16c6ba4db93b0d52b8
                if is_proposal:
                    proposals.append(output.model_dump(by_alias=True))
                await self._audit(
                    AuditRecord(
                        action=f"capability.{capability.name}",
                        entity_type="capability",
                        entity_id=capability.name,
                        after={
                            "subject": actor.subject_id(),
                            "runId": run_id,
                            "proposalOnly": is_proposal or None,
                        },
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
