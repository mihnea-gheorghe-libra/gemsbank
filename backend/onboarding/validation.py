import re

from backend.config import settings
from backend.helpers.errors import ValidationError

USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,30}[a-z0-9]$")
PHONE_PATTERN = re.compile(r"^\+?[0-9 ()\-]{9,20}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")

MIN_PASSWORD_LENGTH = 10
PIN_LENGTH = 6

_SEQUENTIAL = {"0123456789", "9876543210"}


def normalise_username(raw: str) -> str:
    candidate = raw.strip().lower()
    if not USERNAME_PATTERN.match(candidate):
        raise ValidationError(
            "Username must be 3-32 characters: lowercase letters, digits, dot, dash or underscore.",
            details={"field": "username"},
        )
    if candidate == settings.admin_username.strip().lower():
        raise ValidationError("That username is taken.", details={"field": "username"})
    return candidate


def normalise_email(raw: str) -> str:
    candidate = raw.strip().lower()
    if not EMAIL_PATTERN.match(candidate):
        raise ValidationError(
            "That does not look like an email address.", details={"field": "email"}
        )
    return candidate


def normalise_phone(raw: str) -> str:
    candidate = re.sub(r"\s+", " ", raw.strip())
    if not PHONE_PATTERN.match(candidate):
        raise ValidationError("That does not look like a phone number.", details={"field": "phone"})
    return candidate


def validate_password(raw: str, confirmation: str) -> str:
    if raw != confirmation:
        raise ValidationError("Passwords do not match.", details={"field": "passwordConfirm"})
    if len(raw) < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
            details={"field": "password"},
        )
    if not any(c.isalpha() for c in raw) or not any(c.isdigit() for c in raw):
        raise ValidationError(
            "Password must contain at least one letter and one digit.",
            details={"field": "password"},
        )
    return raw


def validate_pin(raw: str, confirmation: str) -> str:
    if raw != confirmation:
        raise ValidationError("The two PINs do not match.", details={"field": "pinConfirm"})
    if len(raw) != PIN_LENGTH or not raw.isdigit():
        raise ValidationError(
            f"The PIN must be exactly {PIN_LENGTH} digits.", details={"field": "pin"}
        )
    if len(set(raw)) == 1:
        raise ValidationError(
            "The PIN cannot be the same digit repeated.", details={"field": "pin"}
        )
    if any(raw in sequence for sequence in _SEQUENTIAL):
        raise ValidationError(
            "The PIN cannot be a run of consecutive digits.", details={"field": "pin"}
        )
    return raw


def mask_email(value: str) -> str:
    local, _, domain = value.partition("@")
    if not domain:
        return "•••"
    visible = local[0] if local else ""
    return f"{visible}{'•' * max(len(local) - 1, 3)}@{domain}"


def mask_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) < 4:
        return "•" * len(digits)
    return f"{value[:6].strip()} ••• {digits[-3:]}"


CNP_PATTERN = re.compile(r"^[1-8]\d{12}$")
CNP_WEIGHTS = (2, 7, 9, 1, 4, 6, 3, 5, 8, 2, 7, 9)


def validate_romanian_cnp(raw: str) -> tuple[bool, str | None, str | None]:
    from datetime import date

    candidate = raw.strip()
    if not CNP_PATTERN.match(candidate):
        return False, None, None
    digits = [int(d) for d in candidate]
    checksum = sum(d * w for d, w in zip(digits[:12], CNP_WEIGHTS)) % 11
    control = 1 if checksum == 10 else checksum
    if digits[12] != control:
        return False, None, None

    century_code = digits[0]
    year_prefix = 1900 if century_code in (1, 2, 7, 8) else 2000 if century_code in (5, 6) else 1800
    year = year_prefix + int(candidate[1:3])
    month = int(candidate[3:5])
    day = int(candidate[5:7])
    try:
        birth_date = date(year, month, day)
    except ValueError:
        return False, None, None

    gender = "M" if century_code in (1, 3, 5, 7) else "F"
    return True, birth_date.isoformat(), gender


def mask_cnp(value: str) -> str:
    cleaned = re.sub(r"\D", "", value)
    if len(cleaned) != 13:
        return "•••••••••••••"
    return f"{cleaned[:5]}{'•' * 8}"

