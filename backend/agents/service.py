from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Protocol

from backend.agents.adapters import AzureChatCompleter
from backend.agents.base import AgentAnswer
from backend.agents.support import SupportAgent
from backend.capabilities.service import get_capabilities_service
from backend.config import settings
from backend.database.records import write_audit
from backend.database.repositories import MongoRateLimitStore, RateLimitHit
from backend.helpers.context import Actor
from backend.helpers.errors import RateLimitedError


class RateLimitStore(Protocol):
    async def bump(self, doc_id: str, now: datetime, window_seconds: int) -> RateLimitHit: ...


class AgentRateLimiter:
    def __init__(
        self, agent_name: str, max_calls: int, window_seconds: int, store: RateLimitStore
    ) -> None:
        self._agent_name = agent_name
        self._max_calls = max_calls
        self._window_seconds = window_seconds
        self._store = store

    async def check(self, key: str) -> None:
        now = datetime.now(timezone.utc)
        doc_id = f"{self._agent_name}:{key}"
        hit = await self._store.bump(doc_id, now, self._window_seconds)

        if hit.count > self._max_calls:
            retry_after = hit.window_start + timedelta(seconds=self._window_seconds) - now
            raise RateLimitedError(
                "Too many questions in a short time. Try again in a bit.",
                details={"retryAfterSeconds": max(int(retry_after.total_seconds()), 0)},
            )


class SupportService:
    def __init__(self, agent: SupportAgent, limiter: AgentRateLimiter) -> None:
        self._agent = agent
        self._limiter = limiter

    async def ask(self, user_id: str, question: str) -> AgentAnswer:
        await self._limiter.check(user_id)
        agent_actor = Actor(kind="agent", id="support-agent", on_behalf_of=user_id)
        return await self._agent.ask(agent_actor, question)


@lru_cache(maxsize=1)
def get_support_service() -> SupportService:
    agent = SupportAgent(
        chat=AzureChatCompleter(settings),
        capabilities=get_capabilities_service(),
        audit=write_audit,
    )
    limiter = AgentRateLimiter(
        agent_name="support",
        max_calls=settings.agent_rate_limit_max_calls,
        window_seconds=settings.agent_rate_limit_window_seconds,
        store=MongoRateLimitStore(),
    )
    return SupportService(agent, limiter)
