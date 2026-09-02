import base64
import binascii
from datetime import datetime

from backend.helpers.errors import ValidationError


def encode_cursor(moment: datetime, record_id: str) -> str:
    raw = f"{moment.isoformat()}|{record_id}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(raw: str | None) -> tuple[datetime, str] | None:
    if not raw:
        return None
    try:
        decoded = base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8")
        moment, _, record_id = decoded.partition("|")
        return datetime.fromisoformat(moment), record_id
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ValidationError(
            "That page cursor is not one we issued.", details={"field": "cursor"}
        ) from exc
