import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from backend.agents.adapters import DEFAULT_RETRY_AFTER_SECONDS
from backend.config import Settings
from backend.helpers.errors import DeliveryError, RateLimitedError, ValidationError

SUPPORTED_CONTENT_TYPES: dict[str, str] = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/mpga": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/flac": "flac",
}

LOCALES: dict[str, str] = {"ro": "ro-RO", "en": "en-US"}
SUPPORTED_LANGUAGES = frozenset(LOCALES)
TRANSCRIBE_PATH = "/speechtotext/transcriptions:transcribe"


@dataclass(slots=True)
class Transcript:
    text: str


class Transcriber(Protocol):
    async def transcribe(
        self, audio: bytes, content_type: str, language: str | None
    ) -> Transcript: ...


def extension_for(content_type: str) -> str:
    base = content_type.split(";")[0].strip().lower()
    extension = SUPPORTED_CONTENT_TYPES.get(base)
    if extension is None:
        raise ValidationError(
            "That audio format is not supported.",
            details={"field": "audio", "contentType": base},
        )
    return extension


def candidate_locales(language: str | None) -> list[str]:
    primary = LOCALES.get(language or "")
    rest = [locale for locale in LOCALES.values() if locale != primary]
    return ([primary] if primary else []) + rest


def speech_base_url(config: Settings) -> str:
    endpoint = (config.azure_speech_endpoint or "").strip().rstrip("/")
    if endpoint:
        return endpoint
    region = (config.azure_speech_region or "").strip().lower()
    if region:
        return f"https://{region}.api.cognitive.microsoft.com"
    raise RuntimeError(
        "Azure speech-to-text is not configured. Set AZURE_SPEECH_ENDPOINT or "
        "AZURE_SPEECH_REGION, plus AZURE_SPEECH_API_KEY."
    )


def combined_text(payload: dict[str, Any]) -> str:
    phrases = payload.get("combinedPhrases")
    if not isinstance(phrases, list):
        return ""
    spoken = [
        phrase["text"].strip()
        for phrase in phrases
        if isinstance(phrase, dict) and isinstance(phrase.get("text"), str)
    ]
    return " ".join(part for part in spoken if part)


class AzureSpeechTranscriber:
    def __init__(self, config: Settings) -> None:
        if not config.azure_speech_api_key:
            raise RuntimeError(
                "Azure speech-to-text is not configured. Set AZURE_SPEECH_API_KEY."
            )
        self._url = speech_base_url(config) + TRANSCRIBE_PATH
        self._api_key: str = config.azure_speech_api_key
        self._api_version = config.azure_speech_api_version
        self._timeout = config.speech_timeout_seconds

    async def transcribe(
        self, audio: bytes, content_type: str, language: str | None
    ) -> Transcript:
        definition = json.dumps(
            {
                "locales": candidate_locales(language),
                "profanityFilterMode": "None",
            }
        )
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self._timeout)) as client:
                response = await client.post(
                    self._url,
                    params={"api-version": self._api_version},
                    headers={"Ocp-Apim-Subscription-Key": self._api_key},
                    files={"audio": (f"voice.{extension_for(content_type)}", audio, content_type)},
                    data={"definition": definition},
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise error_for_status(exc, self._url) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise DeliveryError(
                "The speech service did not answer. Try again in a moment.",
                details={"url": self._url},
            ) from exc
        if not isinstance(payload, dict):
            raise DeliveryError(
                "The speech service answered in an unexpected shape.",
                details={"url": self._url},
            )
        return Transcript(text=combined_text(payload))


def retry_after_seconds(response: httpx.Response) -> int:
    raw = response.headers.get("retry-after")
    if raw is None:
        return DEFAULT_RETRY_AFTER_SECONDS
    try:
        return max(1, int(float(raw)))
    except (TypeError, ValueError):
        return DEFAULT_RETRY_AFTER_SECONDS


def error_for_status(
    exc: httpx.HTTPStatusError, url: str
) -> DeliveryError | RateLimitedError | ValidationError:
    status = exc.response.status_code
    if status in (400, 415):
        return ValidationError(
            "That recording could not be transcribed.",
            details={"field": "audio", "status": status},
        )
    if status == 429:
        return RateLimitedError(
            "The speech service is busy right now. Try again in a moment.",
            details={"retryAfterSeconds": retry_after_seconds(exc.response)},
        )
    if status == 404:
        return DeliveryError(
            "The speech service did not answer. Try again in a moment.",
            details={
                "url": url,
                "hint": "Wrong speech endpoint: clear AZURE_SPEECH_ENDPOINT and set "
                "AZURE_SPEECH_REGION instead.",
            },
        )
    return DeliveryError(
        "The speech service did not answer. Try again in a moment.",
        details={"url": url, "status": status},
    )
