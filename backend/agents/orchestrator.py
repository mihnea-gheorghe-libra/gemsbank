import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from backend.agents.adapters import ChatCompleter
from backend.agents.base import AgentAnswer, AuditSink, ToolCallingAgent
from backend.database.records import AuditRecord
from backend.helpers.context import Actor, get_correlation_id, log_event, new_id

logger = logging.getLogger(__name__)

MAX_WORKERS_PER_QUESTION = 3

ESCALATION_TOOL = "escalate_to_human"

SYSTEM_PROMPT = (
    "You are the GEMS request router. Your ONLY function is to route the customer's question "
    "to the appropriate specialist by calling the corresponding tool function.\n\n"
    "CRITICAL RULES:\n"
    "1. You must ALWAYS call at least one specialist tool function. NEVER respond with plain text.\n"
    "2. When the customer asks to create, set up, calculate or propose a savings goal (e.g. 'fă-mi un obiectiv', "
    "'vreau să economisesc', 'plan de economisire', 'economii pentru X'), you MUST call `ask_education`.\n"
    "3. When the customer is on the Financial Education screen, questions about savings, budgeting, "
    "or setting goals MUST be routed to `ask_education`.\n"
    "4. Do not invent answers, balances or policies yourself — call the tools.\n\n"
    "The available specialist tools are:\n"
    "- ask_education: financial education, budgeting, personalized savings advice, and preparing savings goals "
    "(obiective de economisire) or automated savings proposals for customer confirmation.\n"
    "- ask_payments: account balances, account details, saved payees, and preparing transfer proposals.\n"
    "- ask_analytics: historical spending breakdowns, cashflow forecasts, month recaps, and spending changes.\n"
    "- ask_support: app FAQ, user guide, customer profile, theme/language preferences, and active sessions.\n"
    "- ask_investments: market prices, ETF, stock and cryptocurrency quotes.\n"
    "- ask_deposits: term deposit products (depozite la termen), interest rates, and maturity estimates.\n"
    "- ask_credits: loans, credit lines, mortgages, and monthly repayment estimates.\n"
    "- ask_cards: bank cards list, freeze, unfreeze, block, limits, and PIN viewing.\n"
    f"- {ESCALATION_TOOL}: hand over to a human support agent when the customer is distressed, complaining, reporting fraud or a lost card.\n\n"
    "Call exactly one specialist tool when one can handle it alone (the normal case). Call two or three only when the question genuinely spans multiple domains. Always pass the customer's question rewritten to be self-contained."
)

WORKER_TOOLS = {
    "ask_payments": "payments",
    "ask_analytics": "analytics",
    "ask_support": "support",
    "ask_education": "education",
    "ask_investments": "investments",
    "ask_deposits": "deposits",
    "ask_credits": "credits",
    "ask_cards": "cards",
}

WORKER_TOOL_DESCRIPTIONS = {
    "ask_payments": "Balances of accounts, totals, saved payees, and preparing transfer proposals.",
    "ask_analytics": "Spending breakdown, historical cashflow forecasts, month recap, and spending changes.",
    "ask_support": "App FAQ, user guide, customer profile, theme/language preferences, and active sessions.",
    "ask_education": (
        "Financial literacy, savings advice, budgeting, and preparing savings goals "
        "(obiective de economisire) or automated savings proposals for customer confirmation."
    ),
    "ask_investments": "Market prices, ETF, stock and cryptocurrency quotes.",
    "ask_deposits": "Term deposit products (depozite la termen), interest rates, and maturity estimates.",
    "ask_credits": "Loans, credit lines, mortgages, and monthly repayment estimates.",
    "ask_cards": "Bank cards list, freeze, unfreeze, block, limits, and PIN viewing.",
}

SCREEN_HINTS = {
    "home": "the Home screen, which shows their balances",
    "payments": "the Payments screen, which shows their accounts and movements",
    "analytics": "the Analytics screen, which shows spending breakdowns",
    "portfolio": "the Portfolio screen, which shows accounts, deposits, investments and credit",
    "cards": "the Cards screen, which shows their cards and limits",
    "settings": "the Settings screen",
    "education": (
        "the Financial Education screen, which offers general financial-literacy content, "
        "savings-goal help, and preparing savings goals (obiective de economisire)"
    ),
}


@dataclass(slots=True)
class OrchestratedAnswer:
    answer: str
    agents_used: list[str] = field(default_factory=list)
    capabilities_used: list[str] = field(default_factory=list)
    proposals: list[dict[str, object]] = field(default_factory=list)
    escalated: bool = False
    escalation_reason: str | None = None
    run_id: str = ""


Worker = ToolCallingAgent
AggregateHook = Callable[[str, list[tuple[str, AgentAnswer]]], Awaitable[str]]


def _tool_defs() -> list[dict[str, object]]:
    tools: list[dict[str, object]] = [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": WORKER_TOOL_DESCRIPTIONS.get(name, name),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": (
                                "The customer's question, rewritten to stand on its own "
                                "without the rest of the conversation."
                            ),
                        }
                    },
                    "required": ["question"],
                },
            },
        }
        for name in sorted(WORKER_TOOLS)
    ]
    tools.append(
        {
            "type": "function",
            "function": {
                "name": ESCALATION_TOOL,
                "description": (
                    "Escalate to a human support agent when the customer asks for a person, "
                    "reports fraud or a lost card, or is distressed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "Why a human is the right next step, in one short sentence.",
                        }
                    },
                    "required": ["reason"],
                },
            },
        }
    )
    return tools


class Orchestrator:
    def __init__(
        self,
        chat: ChatCompleter,
        workers: dict[str, Worker],
        audit: AuditSink,
    ) -> None:
        self._chat = chat
        self._workers = workers
        self._audit = audit

    def _routing_messages(
        self, question: str, history: list[dict[str, str]], screen: str | None
    ) -> list[dict[str, object]]:
        system = SYSTEM_PROMPT
        hint = SCREEN_HINTS.get(screen or "")
        if hint:
            system = f"{system}\nThe customer is currently looking at {hint}. That is a hint "
            system = f"{system}about what they may mean, never a reason to override the question."
        prior: list[dict[str, object]] = [
            {"role": turn["role"], "content": turn["content"]} for turn in history
        ]
        return [
            {"role": "system", "content": system},
            *prior,
            {"role": "user", "content": question},
        ]

    async def ask(
        self,
        actor: Actor,
        question: str,
        history: list[dict[str, str]] | None = None,
        screen: str | None = None,
    ) -> OrchestratedAnswer:
        run_id = new_id()
        correlation_id = get_correlation_id()
        turns = history or []

        plan = await self._chat.complete(
            self._routing_messages(question, turns, screen), _tool_defs()
        )

        escalation_reason: str | None = None
        selected: list[tuple[str, str]] = []
        seen: set[str] = set()

        for call in plan.tool_calls:
            try:
                arguments = json.loads(call.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            if call.name == ESCALATION_TOOL:
                escalation_reason = str(arguments.get("reason") or "").strip() or None
                continue
            worker_name = WORKER_TOOLS.get(call.name)
            if worker_name is None or worker_name in seen:
                continue
            if worker_name not in self._workers:
                continue
            seen.add(worker_name)
            sub_question = str(arguments.get("question") or "").strip() or question
            selected.append((worker_name, sub_question))
            if len(selected) >= MAX_WORKERS_PER_QUESTION:
                break

        if not selected and not escalation_reason:
            fallback_worker = "support"
            q_lower = question.lower()
            if screen == "education" or any(
                w in q_lower for w in ("obiectiv", "economis", "economii", "buget", "goal", "salveaza", "salvez")
            ):
                fallback_worker = "education"
            elif screen == "payments" or any(
                w in q_lower for w in ("transfer", "plata", "plati", "plătește", "trimite", "iban", "sold", "virament")
            ):
                fallback_worker = "payments"
            elif screen == "analytics" or any(
                w in q_lower for w in ("cheltuieli", "statistici", "raport", "analiză", "analiza", "buget")
            ):
                fallback_worker = "analytics"
            elif screen == "cards" or any(
                w in q_lower for w in ("card", "pin", "blocheaza", "blochează", "limita", "limită")
            ):
                fallback_worker = "cards"
            elif screen == "investments" or any(
                w in q_lower for w in ("investi", "bursa", "bursă", "crypto", "bitcoin", "actiune", "acțiune", "acțiuni")
            ):
                fallback_worker = "investments"
            elif screen == "deposits" or any(
                w in q_lower for w in ("depozit", "maturitate")
            ):
                fallback_worker = "deposits"
            elif screen == "credits" or any(
                w in q_lower for w in ("credit", "imprumut", "împrumut", "rata", "rată", "ipotecar")
            ):
                fallback_worker = "credits"

            if fallback_worker in self._workers:
                selected.append((fallback_worker, question))

        if not selected:
            answer = (plan.content or "").strip()
            result = OrchestratedAnswer(
                answer=answer,
                escalated=escalation_reason is not None,
                escalation_reason=escalation_reason,
                run_id=run_id,
            )
            await self._record(actor, question, result, correlation_id)
            return result

        results = await self._run_workers(actor, selected, turns, run_id)

        capabilities: list[str] = []
        proposals: list[dict[str, object]] = []
        for _, worker_answer in results:
            capabilities.extend(worker_answer.capabilities_used)
            proposals.extend(worker_answer.proposals)

        if len(results) == 1:
            text = results[0][1].answer
        else:
            text = await self._aggregate(question, turns, results)

        result = OrchestratedAnswer(
            answer=text,
            agents_used=[name for name, _ in results],
            capabilities_used=capabilities,
            proposals=proposals,
            escalated=escalation_reason is not None,
            escalation_reason=escalation_reason,
            run_id=run_id,
        )
        await self._record(actor, question, result, correlation_id)
        return result

    async def _run_workers(
        self,
        actor: Actor,
        selected: list[tuple[str, str]],
        history: list[dict[str, str]],
        run_id: str,
    ) -> list[tuple[str, AgentAnswer]]:
        async def run(name: str, sub_question: str) -> tuple[str, AgentAnswer] | None:
            worker = self._workers[name]
            worker_actor = Actor(
                kind="agent", id=f"{name}-agent", on_behalf_of=actor.subject_id()
            )
            try:
                answer = await worker.ask(
                    worker_actor, sub_question, history=history, run_id=run_id
                )
            except Exception:
                logger.exception(
                    "orchestrator.worker_failed",
                    extra={"context": {"worker": name, "runId": run_id}},
                )
                return None
            return name, answer

        if len(selected) == 1:
            name, sub_question = selected[0]
            single = await run(name, sub_question)
            return [single] if single else []

        gathered = await asyncio.gather(
            *(run(name, sub_question) for name, sub_question in selected)
        )
        return [item for item in gathered if item is not None]

    async def _aggregate(
        self,
        question: str,
        history: list[dict[str, str]],
        results: list[tuple[str, AgentAnswer]],
    ) -> str:
        findings = "\n\n".join(
            f"[{name}]\n{answer.answer}" for name, answer in results if answer.answer
        )
        if not findings.strip():
            return "\n\n".join(answer.answer for _, answer in results if answer.answer)
        prior: list[dict[str, object]] = [
            {"role": turn["role"], "content": turn["content"]} for turn in history
        ]
        messages: list[dict[str, object]] = [
            {
                "role": "system",
                "content": (
                    "You are GEMS writing the final reply to the customer. Below are findings "
                    "gathered to answer the customer's question. Merge them into one clear, "
                    "helpful, and concise reply. Use only the figures, dates, and amounts "
                    "given in the findings — never recalculate or reformat them. Answer in the "
                    "language the customer used. Never mention internal tools, agents, "
                    "specialists, or this background process."
                ),
            },
            *prior,
            {"role": "user", "content": f"{question}\n\n---\n{findings}"},
        ]
        merged = await self._chat.complete(messages, [])
        if merged.content and merged.content.strip():
            return merged.content.strip()
        return "\n\n".join(answer.answer for _, answer in results if answer.answer)

    async def _record(
        self,
        actor: Actor,
        question: str,
        result: OrchestratedAnswer,
        correlation_id: str,
    ) -> None:
        await self._audit(
            AuditRecord(
                action="agents.orchestrator.answered",
                entity_type="agent_run",
                entity_id=result.run_id,
                after={
                    "subject": actor.subject_id(),
                    "question": question,
                    "answer": result.answer,
                    "agentsUsed": result.agents_used,
                    "capabilitiesUsed": result.capabilities_used,
                    "escalated": result.escalated,
                    "escalationReason": result.escalation_reason,
                },
            ),
            actor,
            correlation_id,
        )
        log_event(
            logger,
            "agents.orchestrator.answered",
            actor=actor.label(),
            subject=actor.subject_id(),
            runId=result.run_id,
            agents=result.agents_used,
            capabilities=result.capabilities_used,
            escalated=result.escalated,
        )
