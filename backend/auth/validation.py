import re

from backend.helpers.errors import ValidationError

USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,30}[a-z0-9]$")

MIN_PASSWORD_LENGTH = 10
PIN_LENGTH = 6


def normalise_username(raw: str) -> str:
    candidate = raw.strip().lower()
    if not USERNAME_PATTERN.match(candidate):
        raise ValidationError(
            "Enter the username you chose when you opened the account.",
            details={"field": "username"},
        )
    return candidate


def validate_pin_shape(raw: str) -> str:
    candidate = raw.strip()
    if len(candidate) != PIN_LENGTH or not candidate.isdigit():
        raise ValidationError(
            f"The PIN is exactly {PIN_LENGTH} digits.", details={"field": "pin"}
        )
    return candidate


def validate_new_password(raw: str, confirmation: str) -> str:
    if raw != confirmation:
        raise ValidationError(
            "The two passwords do not match.", details={"field": "passwordConfirmation"}
        )
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


def mask_email(value: str) -> str:
    local, _, domain = value.partition("@")
    if not domain:
        return "•••"
    visible = local[0] if local else ""
    return f"{visible}{'•' * max(len(local) - 1, 3)}@{domain}"
