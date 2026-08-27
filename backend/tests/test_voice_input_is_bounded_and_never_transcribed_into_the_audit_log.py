import pytest

from backend.agents.transcription import Transcript
from backend.agents.transcription_service import TranscriptionService
from backend.database.records import AuditRecord
from backend.helpers.context import Actor
from backend.helpers.errors import ValidationError

SPOKEN = "trimite 200 lei catre Ionescu John"


class _FakeTranscriber:
    def __init__(self, text: str = SPOKEN) -> None:
        self.calls: list[tuple[bytes, str, str | None]] = []
        self._text = text

    async def transcribe(
        self, audio: bytes, content_type: str, language: str | None
    ) -> Transcript:
        self.calls.append((audio, content_type, language))
        return Transcript(text=self._text)


class _FakeAudit:
    def __init__(self) -> None:
        self.records: list[tuple[AuditRecord, Actor]] = []

    async def __call__(
        self, record: AuditRecord, actor: Actor, correlation_id: str
    ) -> None:
        self.records.append((record, actor))


def _service(
    transcriber: _FakeTranscriber, audit: _FakeAudit, max_bytes: int = 1000
) -> TranscriptionService:
    return TranscriptionService(
        transcriber=transcriber, audit=audit, max_bytes=max_bytes
    )


async def test_a_recording_over_the_cap_never_reaches_the_speech_service() -> None:
    transcriber = _FakeTranscriber()
    service = _service(transcriber, _FakeAudit(), max_bytes=10)

    with pytest.raises(ValidationError):
        await service.transcribe("user-1", b"x" * 11, "audio/webm", "ro")

    assert transcriber.calls == []


async def test_an_empty_recording_never_reaches_the_speech_service() -> None:
    transcriber = _FakeTranscriber()
    service = _service(transcriber, _FakeAudit())

    with pytest.raises(ValidationError):
        await service.transcribe("user-1", b"", "audio/webm", "ro")

    assert transcriber.calls == []


async def test_an_unsupported_audio_format_never_reaches_the_speech_service() -> None:
    transcriber = _FakeTranscriber()
    service = _service(transcriber, _FakeAudit())

    with pytest.raises(ValidationError):
        await service.transcribe("user-1", b"payload", "application/pdf", "ro")

    assert transcriber.calls == []


async def test_the_clip_is_forwarded_untouched_with_its_own_content_type() -> None:
    transcriber = _FakeTranscriber()
    service = _service(transcriber, _FakeAudit())

    await service.transcribe("user-1", b"payload", "audio/webm;codecs=opus", "ro")

    assert transcriber.calls == [(b"payload", "audio/webm;codecs=opus", "ro")]


async def test_the_audit_entry_counts_the_words_without_keeping_them() -> None:
    audit = _FakeAudit()
    service = _service(_FakeTranscriber(), audit)

    transcript = await service.transcribe("user-1", b"payload", "audio/webm;codecs=opus", "ro")

    assert transcript.text == SPOKEN
    record, actor = audit.records[0]
    assert record.action == "agents.voice.transcribed"
    assert actor.kind == "agent"
    assert actor.on_behalf_of == "user-1"
    assert record.after == {
        "subject": actor.subject_id(),
        "bytes": len(b"payload"),
        "contentType": "audio/webm;codecs=opus",
        "language": "ro",
        "characters": len(SPOKEN),
    }
    assert SPOKEN not in str(record.model_dump())


async def test_an_unknown_language_hint_is_dropped_rather_than_forwarded_as_is() -> None:
    audit = _FakeAudit()
    service = _service(_FakeTranscriber(), audit)

    await service.transcribe("user-1", b"payload", "audio/webm", "klingon")

    record, _ = audit.records[0]
    assert record.after is not None
    assert record.after["language"] is None
