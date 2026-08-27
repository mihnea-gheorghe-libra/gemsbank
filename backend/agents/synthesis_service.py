from functools import lru_cache

from backend.agents.base import AuditSink
from backend.agents.synthesis import (
    AzureSpeechSynthesizer,
    Synthesizer,
)
from backend.config import settings
from backend.database.records import AuditRecord, write_audit
from backend.helpers.context import Actor, get_correlation_id, new_id
from backend.helpers.errors import ValidationError


class SynthesisService:
    def __init__(
        self, synthesizer: Synthesizer, audit: AuditSink, max_chars: int
    ) -> None:
        self._synthesizer = synthesizer
        self._audit = audit
        self._max_chars = max_chars

    async def synthesize(
        self,
        user_id: str,
        text: str,
        language: str | None = None,
        voice: str | None = None,
    ) -> bytes:
        clean_text = (text or "").strip()
        if not clean_text:
            raise ValidationError(
                "The text to synthesize is empty.", details={"field": "text"}
            )
        if len(clean_text) > self._max_chars:
            raise ValidationError(
                "The text to synthesize is too long.",
                details={"field": "text", "maxChars": self._max_chars},
            )

        actor = Actor(kind="agent", id="voice-output", on_behalf_of=user_id)
        audio_bytes = await self._synthesizer.synthesize(clean_text, language, voice)
        await self._audit(
            AuditRecord(
                action="agents.voice.synthesized",
                entity_type="voice_output",
                entity_id=new_id(),
                after={
                    "subject": actor.subject_id(),
                    "characters": len(clean_text),
                    "language": language,
                    "voice": voice,
                    "bytes": len(audio_bytes),
                },
            ),
            actor,
            get_correlation_id(),
        )
        return audio_bytes


@lru_cache(maxsize=1)
def get_synthesis_service() -> SynthesisService:
    return SynthesisService(
        synthesizer=AzureSpeechSynthesizer(settings),
        audit=write_audit,
        max_chars=settings.speech_tts_max_chars,
    )
