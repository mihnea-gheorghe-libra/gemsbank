import html
from typing import Protocol

import httpx

from backend.agents.adapters import DEFAULT_RETRY_AFTER_SECONDS
from backend.config import Settings
from backend.helpers.errors import DeliveryError, RateLimitedError, ValidationError

LOCALES: dict[str, str] = {"ro": "ro-RO", "en": "en-US"}
DEFAULT_VOICES: dict[str, str] = {
    "ro-RO": "ro-RO-AlinaNeural",
    "en-US": "en-US-JennyNeural",
}
TTS_PATH = "/cognitiveservices/v1"
OUTPUT_FORMAT = "audio-16khz-128kbitrate-mono-mp3"


class Synthesizer(Protocol):
    async def synthesize(
        self, text: str, language: str | None, voice: str | None = None
    ) -> bytes: ...


def xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def resolve_voice_and_locale(
    language: str | None,
    voice: str | None = None,
    config: Settings | None = None,
) -> tuple[str, str]:
    lang_key = (language or "").strip().lower()
    if lang_key.startswith("ro"):
        locale = "ro-RO"
        default_voice = (
            config.azure_speech_tts_voice_ro
            if config
            else DEFAULT_VOICES["ro-RO"]
        )
    elif lang_key.startswith("en"):
        locale = "en-US"
        default_voice = (
            config.azure_speech_tts_voice_en
            if config
            else DEFAULT_VOICES["en-US"]
        )
    else:
        locale = "ro-RO"
        default_voice = (
            config.azure_speech_tts_voice_ro
            if config
            else DEFAULT_VOICES["ro-RO"]
        )

    selected_voice = voice.strip() if voice and voice.strip() else default_voice
    return locale, selected_voice


def build_ssml(text: str, locale: str, voice: str) -> str:
    escaped_text = xml_escape(text)
    return (
        f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' "
        f"xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='{locale}'>"
        f"<voice xml:lang='{locale}' name='{voice}'>{escaped_text}</voice>"
        f"</speak>"
    )


def speech_tts_url(config: Settings) -> str:
    endpoint = (config.azure_speech_endpoint or "").strip().rstrip("/")
    if endpoint:
        if endpoint.endswith(TTS_PATH):
            return endpoint
        return endpoint + TTS_PATH
    region = (config.azure_speech_region or "").strip().lower()
    if region:
        return f"https://{region}.tts.speech.microsoft.com{TTS_PATH}"
    raise RuntimeError(
        "Azure speech synthesis is not configured. Set AZURE_SPEECH_ENDPOINT or "
        "AZURE_SPEECH_REGION, plus AZURE_SPEECH_API_KEY."
    )


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
            "That text could not be synthesized into speech.",
            details={"field": "text", "status": status},
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
                "hint": "Wrong speech endpoint: check AZURE_SPEECH_ENDPOINT or "
                "AZURE_SPEECH_REGION.",
            },
        )
    return DeliveryError(
        "The speech service did not answer. Try again in a moment.",
        details={"url": url, "status": status},
    )


class AzureSpeechSynthesizer:
    def __init__(self, config: Settings) -> None:
        if not config.azure_speech_api_key:
            raise RuntimeError(
                "Azure speech synthesis is not configured. Set AZURE_SPEECH_API_KEY."
            )
        self._url = speech_tts_url(config)
        self._api_key: str = config.azure_speech_api_key
        self._timeout = config.speech_timeout_seconds
        self._config = config

    async def synthesize(
        self, text: str, language: str | None, voice: str | None = None
    ) -> bytes:
        locale, selected_voice = resolve_voice_and_locale(
            language, voice, self._config
        )
        ssml = build_ssml(text, locale, selected_voice)
        headers = {
            "Ocp-Apim-Subscription-Key": self._api_key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": OUTPUT_FORMAT,
            "User-Agent": "GemsBank",
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self._timeout)) as client:
                response = await client.post(
                    self._url,
                    headers=headers,
                    content=ssml.encode("utf-8"),
                )
                response.raise_for_status()
                return response.content
        except httpx.HTTPStatusError as exc:
            raise error_for_status(exc, self._url) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise DeliveryError(
                "The speech service did not answer. Try again in a moment.",
                details={"url": self._url},
            ) from exc
