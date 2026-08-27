from functools import lru_cache

from backend.agents.base import AuditSink
from backend.agents.transcription import (
    SUPPORTED_LANGUAGES,
    AzureSpeechTranscriber,
    Transcriber,
    Transcript,
    extension_for,
)
from backend.config import settings
from backend.database.records import AuditRecord, write_audit
from backend.helpers.context import Actor, get_correlation_id, new_id
from backend.helpers.errors import ValidationError


class TranscriptionService:
    def __init__(
        self, transcriber: Transcriber, audit: AuditSink, max_bytes: int
    ) -> None:
        self._transcriber = transcriber
        self._audit = audit
        self._max_bytes = max_bytes

    async def transcribe(
        self, user_id: str, audio: bytes, content_type: str, language: str | None
    ) -> Transcript:
        if not audio:
            raise ValidationError(
                "The recording is empty.", details={"field": "audio"}
            )
        if len(audio) > self._max_bytes:
            raise ValidationError(
                "The recording is too long.",
                details={"field": "audio", "maxBytes": self._max_bytes},
            )
        extension_for(content_type)

        actor = Actor(kind="agent", id="voice-input", on_behalf_of=user_id)
        transcript = await self._transcriber.transcribe(audio, content_type, language)
        await self._audit(
            AuditRecord(
                action="agents.voice.transcribed",
                entity_type="voice_input",
                entity_id=new_id(),
                after={
                    "subject": actor.subject_id(),
                    "bytes": len(audio),
                    "contentType": content_type,
                    "language": language if language in SUPPORTED_LANGUAGES else None,
                    "characters": len(transcript.text),
                },
            ),
            actor,
            get_correlation_id(),
        )
        return transcript


@lru_cache(maxsize=1)
def get_transcription_service() -> TranscriptionService:
    return TranscriptionService(
        transcriber=AzureSpeechTranscriber(settings),
        audit=write_audit,
        max_bytes=settings.speech_max_upload_bytes,
    )
