from functools import lru_cache

from backend.agents.adapters import AzureChatCompleter
from backend.agents.base import AgentAnswer
from backend.agents.payments import PaymentsAgent
from backend.agents.service import AgentRateLimiter
from backend.capabilities.service import get_capabilities_service
from backend.config import settings
from backend.database.records import write_audit
from backend.database.repositories import MongoRateLimitStore
from backend.helpers.context import Actor


class PaymentsAgentService:
    def __init__(self, agent: PaymentsAgent, limiter: AgentRateLimiter) -> None:
        self._agent = agent
        self._limiter = limiter

    async def ask(self, user_id: str, question: str) -> AgentAnswer:
        await self._limiter.check(user_id)
        agent_actor = Actor(kind="agent", id="payments-agent", on_behalf_of=user_id)
        return await self._agent.ask(agent_actor, question)


@lru_cache(maxsize=1)
def get_payments_agent_service() -> PaymentsAgentService:
    agent = PaymentsAgent(
        chat=AzureChatCompleter(settings),
        capabilities=get_capabilities_service(),
        audit=write_audit,
    )
    limiter = AgentRateLimiter(
        agent_name="payments",
        max_calls=settings.agent_rate_limit_max_calls,
        window_seconds=settings.agent_rate_limit_window_seconds,
        store=MongoRateLimitStore(),
    )
    return PaymentsAgentService(agent, limiter)
