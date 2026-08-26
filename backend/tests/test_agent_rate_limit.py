from datetime import datetime, timedelta, timezone

import pytest

from backend.agents.service import AgentRateLimiter
from backend.database.repositories import RateLimitHit
from backend.helpers.errors import RateLimitedError


class _FakeRateLimitStore:
    def __init__(self) -> None:
        self._windows: dict[str, tuple[datetime, int]] = {}

    async def bump(self, doc_id: str, now: datetime, window_seconds: int) -> RateLimitHit:
        window_start, count = self._windows.get(doc_id, (now, 0))
        if now - window_start > timedelta(seconds=window_seconds):
            window_start, count = now, 0
        count += 1
        self._windows[doc_id] = (window_start, count)
        return RateLimitHit(count=count, window_start=window_start)


def _limiter(max_calls: int, window_seconds: int) -> AgentRateLimiter:
    return AgentRateLimiter(
        agent_name="test-agent",
        max_calls=max_calls,
        window_seconds=window_seconds,
        store=_FakeRateLimitStore(),
    )


async def test_rate_limiter_allows_up_to_the_configured_number_of_calls_in_the_window() -> None:
    limiter = _limiter(max_calls=3, window_seconds=60)
    await limiter.check("user-1")
    await limiter.check("user-1")
    await limiter.check("user-1")


async def test_rate_limiter_rejects_the_call_past_the_limit() -> None:
    limiter = _limiter(max_calls=2, window_seconds=60)
    await limiter.check("user-1")
    await limiter.check("user-1")
    with pytest.raises(RateLimitedError):
        await limiter.check("user-1")


async def test_rate_limiter_tracks_each_user_independently() -> None:
    limiter = _limiter(max_calls=1, window_seconds=60)
    await limiter.check("user-1")
    await limiter.check("user-2")


async def test_rate_limiter_allows_a_new_call_once_the_window_has_passed(monkeypatch) -> None:
    store = _FakeRateLimitStore()
    limiter = AgentRateLimiter(
        agent_name="test-agent", max_calls=1, window_seconds=10, store=store
    )
    current = [datetime(2026, 1, 1, tzinfo=timezone.utc)]

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return current[0]

    import backend.agents.service as agent_service_module

    monkeypatch.setattr(agent_service_module, "datetime", _FixedDatetime)

    await limiter.check("user-1")

    with pytest.raises(RateLimitedError):
        await limiter.check("user-1")

    current[0] = current[0] + timedelta(seconds=11)
    await limiter.check("user-1")
