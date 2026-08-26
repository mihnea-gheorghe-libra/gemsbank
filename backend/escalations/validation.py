from backend.helpers.errors import ValidationError

MAX_QUESTION_CHARS = 500
MAX_REASON_CHARS = 300


def normalise_question(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise ValidationError(
            "Tell us what you need help with.", details={"field": "question"}
        )
    return text[:MAX_QUESTION_CHARS]


def normalise_reason(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = raw.strip()
    return text[:MAX_REASON_CHARS] or None
