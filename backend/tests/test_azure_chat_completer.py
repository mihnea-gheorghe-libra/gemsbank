from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import BadRequestError, RateLimitError

from backend.agents.adapters import (
    CONTENT_FILTER_REFUSAL,
    DEFAULT_RETRY_AFTER_SECONDS,
    AzureChatCompleter,
)
from backend.helpers.errors import RateLimitedError


def _bad_request_error(code: str) -> BadRequestError:
    request = httpx.Request("POST", "https://example.test/chat/completions")
    response = httpx.Response(400, request=request)
    return BadRequestError("blocked", response=response, body={"code": code, "message": "blocked"})


def _completer_with(create: AsyncMock) -> AzureChatCompleter:
    completer = AzureChatCompleter.__new__(AzureChatCompleter)
    completer._client = SimpleNamespace(  # type: ignore[attr-defined]
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    completer._deployment = "test-deployment"  # type: ignore[attr-defined]
    return completer


async def test_a_content_filter_block_becomes_a_safe_refusal_instead_of_a_500() -> None:
    completer = _completer_with(AsyncMock(side_effect=_bad_request_error("content_filter")))

    result = await completer.complete([{"role": "user", "content": "hi"}], [])

    assert result.content == CONTENT_FILTER_REFUSAL
    assert result.tool_calls == []


async def test_a_bad_request_that_is_not_a_content_filter_block_still_propagates() -> None:
    completer = _completer_with(AsyncMock(side_effect=_bad_request_error("invalid_request_error")))

    with pytest.raises(BadRequestError):
        await completer.complete([{"role": "user", "content": "hi"}], [])


def _rate_limit_error(retry_after: str | None) -> RateLimitError:
    request = httpx.Request("POST", "https://example.test/chat/completions")
    headers = {"retry-after": retry_after} if retry_after is not None else {}
    response = httpx.Response(429, request=request, headers=headers)
    return RateLimitError("slow down", response=response, body=None)


async def test_the_providers_own_limit_becomes_the_same_friendly_error_as_before() -> None:
    completer = _completer_with(AsyncMock(side_effect=_rate_limit_error("42")))

    with pytest.raises(RateLimitedError) as caught:
        await completer.complete([{"role": "user", "content": "hi"}], [])

    assert caught.value.details["retryAfterSeconds"] == 42
    assert caught.value.http_status == 429


async def test_a_provider_limit_without_a_retry_header_still_suggests_a_wait() -> None:
    completer = _completer_with(AsyncMock(side_effect=_rate_limit_error(None)))

    with pytest.raises(RateLimitedError) as caught:
        await completer.complete([{"role": "user", "content": "hi"}], [])

    assert caught.value.details["retryAfterSeconds"] == DEFAULT_RETRY_AFTER_SECONDS


async def test_an_unparseable_retry_header_does_not_crash_the_request() -> None:
    completer = _completer_with(AsyncMock(side_effect=_rate_limit_error("soon-ish")))

    with pytest.raises(RateLimitedError) as caught:
        await completer.complete([{"role": "user", "content": "hi"}], [])

    assert caught.value.details["retryAfterSeconds"] == DEFAULT_RETRY_AFTER_SECONDS
