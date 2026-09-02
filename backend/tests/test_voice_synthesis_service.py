import pytest

from backend.agents.synthesis_service import SynthesisService
from backend.database.records import AuditRecord
from backend.helpers.context import Actor
from backend.helpers.errors import ValidationError

SAMPLE_TEXT = "Soldul contului tău curent este de 2.500,00 RON."
SYNTHESIZED_AUDIO = b"fake-mp3-audio-bytes-12345"


class _FakeSynthesizer:
    def __init__(self, audio: bytes = SYNTHESIZED_AUDIO) -> None:
        self.calls: list[tuple[str, str | None, str | None]] = []
        self._audio = audio

    async def synthesize(
        self, text: str, language: str | None, voice: str | None = None
    ) -> bytes:
        self.calls.append((text, language, voice))
        return self._audio


class _FakeAudit:
    def __init__(self) -> None:
        self.records: list[tuple[AuditRecord, Actor]] = []

    async def __call__(
        self, record: AuditRecord, actor: Actor, correlation_id: str
    ) -> None:
        self.records.append((record, actor))


def _service(
    synthesizer: _FakeSynthesizer, audit: _FakeAudit, max_chars: int = 5000
) -> SynthesisService:
    return SynthesisService(
        synthesizer=synthesizer, audit=audit, max_chars=max_chars
    )


async def test_an_empty_text_never_reaches_the_speech_service() -> None:
    synthesizer = _FakeSynthesizer()
    service = _service(synthesizer, _FakeAudit())

    with pytest.raises(ValidationError):
        await service.synthesize("user-1", "   ", "ro")

    assert synthesizer.calls == []


async def test_text_over_the_character_cap_never_reaches_the_speech_service() -> None:
    synthesizer = _FakeSynthesizer()
    service = _service(synthesizer, _FakeAudit(), max_chars=10)

    with pytest.raises(ValidationError):
        await service.synthesize("user-1", "a" * 11, "ro")

    assert synthesizer.calls == []


async def test_the_text_is_forwarded_to_synthesizer_cleanly() -> None:
    synthesizer = _FakeSynthesizer()
    service = _service(synthesizer, _FakeAudit())

    audio = await service.synthesize(
        "user-1", "  " + SAMPLE_TEXT + "  ", "ro", "ro-RO-AlinaNeural"
    )

    assert audio == SYNTHESIZED_AUDIO
    assert synthesizer.calls == [(SAMPLE_TEXT, "ro", "ro-RO-AlinaNeural")]


async def test_the_audit_entry_records_character_and_byte_counts() -> None:
    audit = _FakeAudit()
    service = _service(_FakeSynthesizer(), audit)

    await service.synthesize("user-1", SAMPLE_TEXT, "ro", "ro-RO-AlinaNeural")

    assert len(audit.records) == 1
    record, actor = audit.records[0]
    assert record.action == "agents.voice.synthesized"
    assert actor.kind == "agent"
    assert actor.on_behalf_of == "user-1"
    assert record.after == {
        "subject": actor.subject_id(),
        "characters": len(SAMPLE_TEXT),
        "language": "ro",
        "voice": "ro-RO-AlinaNeural",
        "bytes": len(SYNTHESIZED_AUDIO),
    }
