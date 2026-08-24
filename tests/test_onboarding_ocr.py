from datetime import date
import pytest

from backend.onboarding.validation import mask_cnp, validate_romanian_cnp


def test_validate_romanian_cnp_valid_male_1998() -> None:
    is_valid, bdate, gender = validate_romanian_cnp("1980101123452")
    assert is_valid is True
    assert bdate == "1998-01-01"
    assert gender == "M"


def test_validate_romanian_cnp_valid_female_2004() -> None:
    is_valid, bdate, gender = validate_romanian_cnp("6040515123452")
    assert is_valid is True
    assert bdate == "2004-05-15"
    assert gender == "F"


def test_validate_romanian_cnp_invalid_checksum() -> None:
    is_valid, bdate, gender = validate_romanian_cnp("1980101123459")
    assert is_valid is False
    assert bdate is None
    assert gender is None


def test_validate_romanian_cnp_invalid_format() -> None:
    is_valid, _, _ = validate_romanian_cnp("12345")
    assert is_valid is False
    is_valid, _, _ = validate_romanian_cnp("9980101123452")
    assert is_valid is False


def test_validate_romanian_cnp_invalid_calendar_date() -> None:
    is_valid, _, _ = validate_romanian_cnp("1980231123457")
    assert is_valid is False


def test_mask_cnp() -> None:
    assert mask_cnp("1980101123452") == "19801••••••••"
    assert mask_cnp("invalid") == "•••••••••••••"
