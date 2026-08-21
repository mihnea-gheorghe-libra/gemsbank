import re
import secrets

from backend.helpers.errors import ValidationError

IBAN_PATTERN = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$")
GEMS_COUNTRY = "RO"
GEMS_BANK_CODE = "GEMS"
GEMS_SERIAL_DIGITS = 16


def _to_numeric(value: str) -> int:
    return int("".join(str(ord(c) - 55) if c.isalpha() else c for c in value))


def _check_digits(bban: str) -> str:
    remainder = _to_numeric(f"{bban}{GEMS_COUNTRY}00") % 97
    return f"{98 - remainder:02d}"


def normalise_iban(raw: str) -> str:
    candidate = re.sub(r"[\s-]", "", raw).upper()
    if not IBAN_PATTERN.match(candidate):
        raise ValidationError("That does not look like an IBAN.", details={"field": "iban"})
    if _to_numeric(candidate[4:] + candidate[:4]) % 97 != 1:
        raise ValidationError(
            "That IBAN fails its check digits. Retype it.", details={"field": "iban"}
        )
    return candidate


def generate_iban() -> str:
    serial = "".join(str(secrets.randbelow(10)) for _ in range(GEMS_SERIAL_DIGITS))
    bban = f"{GEMS_BANK_CODE}{serial}"
    return f"{GEMS_COUNTRY}{_check_digits(bban)}{bban}"


def is_gems_iban(iban: str) -> bool:
    return iban.startswith(GEMS_COUNTRY) and iban[4:8] == GEMS_BANK_CODE


def format_iban(iban: str) -> str:
    return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))
