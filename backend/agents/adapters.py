from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from openai import AsyncAzureOpenAI, BadRequestError

from backend.config import Settings

CONTENT_FILTER_REFUSAL = "I can't help with that request."


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
