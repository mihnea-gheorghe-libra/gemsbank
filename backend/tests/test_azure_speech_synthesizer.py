import httpx
import pytest

from backend.agents.synthesis import (
    TTS_PATH,
    AzureSpeechSynthesizer,
    build_ssml,
    error_for_status,
    resolve_voice_and_locale,
    speech_tts_url,
    xml_escape,
)
from backend.config import Settings
from backend.helpers.errors import DeliveryError, RateLimitedError, ValidationError


def _settings(**overrides: object) -> Settings:
    from backend.config import settings

    return settings.model_copy(update=overrides)


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.test" + TTS_PATH)
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError("failed", request=request, response=response)


def test_ssml_escapes_xml_special_characters() -> None:
    raw = "Soldul tău este < 100 & ai primit \"500 lei\" de la John's store."
    escaped = xml_escape(raw)

    assert "<" not in escaped
    assert "&lt;" in escaped
    assert "&amp;" in escaped
    assert "&quot;" in escaped
    assert "&apos;" in escaped


def test_build_ssml_contains_locale_voice_and_escaped_text() -> None:
    ssml = build_ssml("Salut & bine ai venit!", "ro-RO", "ro-RO-AlinaNeural")

    assert "xml:lang='ro-RO'" in ssml
    assert "name='ro-RO-AlinaNeural'" in ssml
    assert "Salut &amp; bine ai venit!" in ssml


def test_resolve_voice_and_locale_defaults_for_supported_languages() -> None:
    assert resolve_voice_and_locale("ro") == ("ro-RO", "ro-RO-AlinaNeural")
    assert resolve_voice_and_locale("ro-RO") == ("ro-RO", "ro-RO-AlinaNeural")
    assert resolve_voice_and_locale("en") == ("en-US", "en-US-JennyNeural")
    assert resolve_voice_and_locale("en-US") == ("en-US", "en-US-JennyNeural")


def test_resolve_voice_and_locale_allows_custom_voice_override() -> None:
    assert resolve_voice_and_locale("ro", "ro-RO-EmilNeural") == (
        "ro-RO",
        "ro-RO-EmilNeural",
    )
    assert resolve_voice_and_locale("en", "en-US-GuyNeural") == (
        "en-US",
        "en-US-GuyNeural",
    )


def test_resolve_voice_and_locale_defaults_to_romanian_on_unknown() -> None:
    assert resolve_voice_and_locale(None) == ("ro-RO", "ro-RO-AlinaNeural")
    assert resolve_voice_and_locale("unknown") == ("ro-RO", "ro-RO-AlinaNeural")


def test_speech_tts_url_with_custom_endpoint() -> None:
    config = _settings(
        azure_speech_endpoint="https://gems-speech.cognitiveservices.azure.com/",
        azure_speech_region="westeurope",
    )
    assert (
        speech_tts_url(config)
        == "https://gems-speech.cognitiveservices.azure.com/cognitiveservices/v1"
    )


def test_speech_tts_url_with_region_alone() -> None:
    config = _settings(azure_speech_endpoint=None, azure_speech_region="WestEurope")
    assert (
        speech_tts_url(config)
        == "https://westeurope.tts.speech.microsoft.com/cognitiveservices/v1"
    )


def test_speech_tts_url_fails_when_neither_endpoint_nor_region_is_set() -> None:
    config = _settings(azure_speech_endpoint=None, azure_speech_region=None)
    with pytest.raises(RuntimeError):
        speech_tts_url(config)


def test_azure_speech_synthesizer_fails_when_api_key_missing() -> None:
    config = _settings(azure_speech_api_key=None, azure_speech_region="westeurope")
    with pytest.raises(RuntimeError):
        AzureSpeechSynthesizer(config)


def test_synthesis_error_for_status_mappings() -> None:
    assert isinstance(error_for_status(_status_error(400), "u"), ValidationError)
    assert isinstance(error_for_status(_status_error(415), "u"), ValidationError)
    assert isinstance(error_for_status(_status_error(500), "u"), DeliveryError)


def test_synthesis_rate_limited_status_maps_to_rate_limited_error() -> None:
    request = httpx.Request("POST", "https://example.test" + TTS_PATH)
    response = httpx.Response(429, request=request, headers={"retry-after": "30"})
    exc = httpx.HTTPStatusError("slow down", request=request, response=response)

    error = error_for_status(exc, "u")
    assert isinstance(error, RateLimitedError)
    assert error.details["retryAfterSeconds"] == 30


def test_synthesis_404_gives_helpful_endpoint_hint() -> None:
    error = error_for_status(_status_error(404), "https://example.test")
    assert isinstance(error, DeliveryError)
    assert "AZURE_SPEECH_REGION" in error.details["hint"]
