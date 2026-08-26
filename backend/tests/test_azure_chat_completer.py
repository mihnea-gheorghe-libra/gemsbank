from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import BadRequestError

from backend.agents.adapters import CONTENT_FILTER_REFUSAL, AzureChatCompleter


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
