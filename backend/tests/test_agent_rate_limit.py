import pytest

from backend.agents import service as agent_service_module
from backend.agents.service import AgentRateLimiter
from backend.helpers.errors import RateLimitedError


def test_rate_limiter_allows_up_to_the_configured_number_of_calls_in_the_window() -> None:
    limiter = AgentRateLimiter(max_calls=3, window_seconds=60)
    limiter.check("user-1")
    limiter.check("user-1")
    limiter.check("user-1")


def test_rate_limiter_rejects_the_call_past_the_limit() -> None:
    limiter = AgentRateLimiter(max_calls=2, window_seconds=60)
    limiter.check("user-1")
    limiter.check("user-1")
    with pytest.raises(RateLimitedError):
        limiter.check("user-1")


def test_rate_limiter_tracks_each_user_independently() -> None:
    limiter = AgentRateLimiter(max_calls=1, window_seconds=60)
    limiter.check("user-1")
    limiter.check("user-2")


def test_rate_limiter_allows_a_new_call_once_the_window_has_passed(monkeypatch) -> None:
    current = [0.0]
    monkeypatch.setattr(agent_service_module.time, "monotonic", lambda: current[0])
    limiter = AgentRateLimiter(max_calls=1, window_seconds=10)
    limiter.check("user-1")

    with pytest.raises(RateLimitedError):
        limiter.check("user-1")

    current[0] = 11.0
    limiter.check("user-1")
