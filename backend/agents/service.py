import time
from collections import deque
from functools import lru_cache

from backend.agents.adapters import AzureChatCompleter
from backend.agents.base import AgentAnswer
from backend.agents.support import SupportAgent
from backend.capabilities.service import get_capabilities_service
from backend.config import settings
from backend.database.records import write_audit
from backend.helpers.context import Actor
from backend.helpers.errors import RateLimitedError


class AgentRateLimiter:
    def __init__(self, max_calls: int, window_seconds: int) -> None:
        self._max_calls = max_calls
        self._window_seconds = window_seconds
        self._calls: dict[str, deque[float]] = {}

    def check(self, key: str) -> None:
        now = time.monotonic()
        window_start = now - self._window_seconds
        calls = self._calls.setdefault(key, deque())
        while calls and calls[0] < window_start:
            calls.popleft()
        if len(calls) >= self._max_calls:
            raise RateLimitedError(
                "Too many questions in a short time. Try again in a bit.",
                details={"retryAfterSeconds": int(calls[0] + self._window_seconds - now)},
            )
        calls.append(now)


class SupportService:
    def __init__(self, agent: SupportAgent, limiter: AgentRateLimiter) -> None:
        self._agent = agent
        self._limiter = limiter

    async def ask(self, user_id: str, question: str) -> AgentAnswer:
        self._limiter.check(user_id)
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
        max_calls=settings.agent_rate_limit_max_calls,
        window_seconds=settings.agent_rate_limit_window_seconds,
    )
    return SupportService(agent, limiter)
