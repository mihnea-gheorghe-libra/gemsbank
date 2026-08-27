import httpx
import pytest

from backend.agents.transcription import (
    TRANSCRIBE_PATH,
    candidate_locales,
    combined_text,
    error_for_status,
    speech_base_url,
)
from backend.config import Settings
from backend.helpers.errors import DeliveryError, RateLimitedError, ValidationError


def _settings(**overrides: object) -> Settings:
    from backend.config import settings

    return settings.model_copy(update=overrides)


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.test" + TRANSCRIBE_PATH)
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError("failed", request=request, response=response)


def test_the_spoken_language_is_offered_first_but_never_the_only_candidate() -> None:
    assert candidate_locales("ro") == ["ro-RO", "en-US"]
    assert candidate_locales("en") == ["en-US", "ro-RO"]


def test_an_unknown_language_hint_still_offers_every_locale_the_bank_speaks() -> None:
    assert sorted(candidate_locales(None)) == ["en-US", "ro-RO"]
    assert sorted(candidate_locales("klingon")) == ["en-US", "ro-RO"]


def test_every_recognised_phrase_is_kept_in_order() -> None:
    payload = {"combinedPhrases": [{"text": " trimite 200 lei "}, {"text": "catre John"}]}

    assert combined_text(payload) == "trimite 200 lei catre John"


def test_a_silent_or_malformed_answer_becomes_an_empty_transcript_not_a_crash() -> None:
    assert combined_text({}) == ""
    assert combined_text({"combinedPhrases": []}) == ""
    assert combined_text({"combinedPhrases": [{"text": None}, "junk"]}) == ""


def test_an_explicit_endpoint_wins_over_the_region_shorthand() -> None:
    config = _settings(
        azure_speech_endpoint="https://gems.cognitiveservices.azure.com/",
        azure_speech_region="westeurope",
    )

    assert speech_base_url(config) == "https://gems.cognitiveservices.azure.com"


def test_a_region_alone_is_enough_to_reach_the_speech_service() -> None:
    config = _settings(azure_speech_endpoint=None, azure_speech_region="WestEurope")

    assert speech_base_url(config) == "https://westeurope.api.cognitive.microsoft.com"


def test_neither_endpoint_nor_region_fails_loudly_instead_of_calling_nowhere() -> None:
    config = _settings(azure_speech_endpoint=None, azure_speech_region=None)

    with pytest.raises(RuntimeError):
        speech_base_url(config)


def test_a_rejected_clip_is_the_callers_fault_and_an_outage_is_ours() -> None:
    assert isinstance(error_for_status(_status_error(400), "u"), ValidationError)
    assert isinstance(error_for_status(_status_error(415), "u"), ValidationError)
    assert isinstance(error_for_status(_status_error(500), "u"), DeliveryError)


def test_the_speech_services_own_limit_becomes_the_same_friendly_error_as_the_chat_one() -> None:
    request = httpx.Request("POST", "https://example.test" + TRANSCRIBE_PATH)
    response = httpx.Response(429, request=request, headers={"retry-after": "42"})
    exc = httpx.HTTPStatusError("slow down", request=request, response=response)

    error = error_for_status(exc, "u")

    assert isinstance(error, RateLimitedError)
    assert error.details["retryAfterSeconds"] == 42


def test_a_limit_without_a_usable_retry_header_still_suggests_a_wait() -> None:
    assert error_for_status(_status_error(429), "u").details["retryAfterSeconds"] > 0


def test_a_wrong_endpoint_answers_404_and_the_error_names_the_fix() -> None:
    error = error_for_status(_status_error(404), "https://example.test")

    assert isinstance(error, DeliveryError)
    assert "AZURE_SPEECH_REGION" in error.details["hint"]
