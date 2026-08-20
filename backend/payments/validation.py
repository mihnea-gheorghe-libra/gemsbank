import base64
import binascii
import re
from datetime import datetime

from backend.helpers.errors import ValidationError

REFERENCE_PATTERN = re.compile(r"^[\w \-.,/&'()+]{1,140}$", re.UNICODE)
COUNTERPARTY_PATTERN = re.compile(r"^[^\d<>{}]{2,70}$", re.UNICODE)

CATEGORIES = (
    "transfer",
    "groceries",
    "utilities",
    "transport",
    "entertainment",
    "income",
    "other",
)

DIRECTIONS = {"credit", "debit"}


def normalise_reference(raw: str) -> str:
    candidate = re.sub(r"\s+", " ", raw.strip())
    if not candidate:
        raise ValidationError(
            "Add a short reference so you recognise this payment later.",
            details={"field": "reference"},
        )
    if not REFERENCE_PATTERN.match(candidate):
        raise ValidationError(
            "A reference is up to 140 plain characters.", details={"field": "reference"}
        )
    return candidate


def normalise_counterparty(raw: str) -> str:
    candidate = re.sub(r"\s+", " ", raw.strip())
    if not COUNTERPARTY_PATTERN.match(candidate):
        raise ValidationError(
            "Enter the beneficiary's name as it appears on their account.",
            details={"field": "counterparty"},
        )
    return candidate


def normalise_category(raw: str | None) -> str:
    if raw is None:
        return "transfer"
    candidate = raw.strip().lower()
    if candidate not in CATEGORIES:
        raise ValidationError(
            "That is not a category GEMS knows.",
            details={"field": "category", "allowed": list(CATEGORIES)},
        )
    return candidate


def normalise_direction(raw: str | None) -> str | None:
    if raw is None:
        return None
    candidate = raw.strip().lower()
    if candidate not in DIRECTIONS:
        raise ValidationError(
            "Direction is 'credit' or 'debit'.",
            details={"field": "direction", "allowed": sorted(DIRECTIONS)},
        )
    return candidate


def normalise_search(raw: str | None) -> str | None:
    if raw is None:
        return None
    candidate = raw.strip()
    return candidate[:70] or None


def validate_signature_code(raw: str) -> str:
    candidate = raw.strip()
    if not candidate.isdigit() or len(candidate) != 6:
        raise ValidationError(
            "The signature code is six digits.", details={"field": "code"}
        )
    return candidate


def encode_cursor(posted_at: datetime, transaction_id: str) -> str:
    raw = f"{posted_at.isoformat()}|{transaction_id}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(raw: str | None) -> tuple[datetime, str] | None:
    if not raw:
        return None
    try:
        decoded = base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8")
        moment, _, transaction_id = decoded.partition("|")
        return datetime.fromisoformat(moment), transaction_id
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ValidationError(
            "That page cursor is not one we issued.", details={"field": "cursor"}
        ) from exc


def names_agree(claimed: str, on_file: str) -> bool:
    def tokens(value: str) -> set[str]:
        return {part for part in re.split(r"[^\w]+", value.lower()) if len(part) > 1}

    left, right = tokens(claimed), tokens(on_file)
    if not left or not right:
        return False
    return len(left & right) >= min(len(left), len(right))
