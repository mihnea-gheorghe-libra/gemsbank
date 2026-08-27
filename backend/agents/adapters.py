from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from openai import AsyncAzureOpenAI, BadRequestError, RateLimitError

from backend.config import Settings
from backend.helpers.errors import RateLimitedError

CONTENT_FILTER_REFUSAL = "I can't help with that request."


DEFAULT_RETRY_AFTER_SECONDS = 20


def _retry_after_seconds(exc: RateLimitError) -> int:
    headers = getattr(getattr(exc, "response", None), "headers", None)
    raw: str | None = headers.get("retry-after") if headers else None
    if raw is None:
        return DEFAULT_RETRY_AFTER_SECONDS
    try:
        return max(1, int(float(raw)))
    except (TypeError, ValueError):
        return DEFAULT_RETRY_AFTER_SECONDS


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(slots=True)
class ChatResult:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    message: dict[str, Any] = field(default_factory=dict)


class ChatCompleter(Protocol):
    async def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ChatResult: ...


class AzureChatCompleter:
    def __init__(self, config: Settings) -> None:
        if (
            not config.azure_openai_endpoint
            or not config.azure_openai_api_key
            or not config.azure_openai_deployment
        ):
            raise RuntimeError(
                "Azure OpenAI is not configured. Set AZURE_OPENAI_ENDPOINT, "
                "AZURE_OPENAI_API_KEY and AZURE_OPENAI_DEPLOYMENT."
            )
        self._client = AsyncAzureOpenAI(
            api_key=config.azure_openai_api_key,
            azure_endpoint=config.azure_openai_endpoint,
            api_version=config.azure_openai_api_version,
        )
        self._deployment: str = config.azure_openai_deployment

    async def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ChatResult:
        extra: dict[str, Any] = {"parallel_tool_calls": True} if tools else {}
        try:
            response = await self._client.chat.completions.create(
                model=self._deployment,
                messages=cast(Any, messages),
                tools=cast(Any, tools or None),
                **extra,
            )
        except RateLimitError as exc:
            raise RateLimitedError(
                "GEMS is handling a lot of questions right now. Try again in a moment.",
                details={"retryAfterSeconds": _retry_after_seconds(exc)},
            ) from exc
        except BadRequestError as exc:
            if exc.code != "content_filter":
                raise
            return ChatResult(
                content=CONTENT_FILTER_REFUSAL,
                message={"role": "assistant", "content": CONTENT_FILTER_REFUSAL},
            )
        choice = response.choices[0].message
        calls = [
            ToolCall(id=call.id, name=call.function.name, arguments=call.function.arguments)
            for call in (choice.tool_calls or [])
        ]
        return ChatResult(
            content=choice.content,
            tool_calls=calls,
            message=choice.model_dump(exclude_none=True),
        )
