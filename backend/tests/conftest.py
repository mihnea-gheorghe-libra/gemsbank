import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _web_dir() -> str:
    candidates = [os.environ.get("WEB_DIR"), str(_REPO_ROOT / "frontend"), "/web"]
    for candidate in candidates:
        if candidate and (Path(candidate) / "help.html").is_file():
            return candidate
    return str(_REPO_ROOT / "frontend")


_TEST_ENV = {
    "WEB_DIR": _web_dir(),
    "OTP_TTL_SECONDS": "120",
    "OTP_RESEND_COOLDOWN_SECONDS": "30",
    "OTP_MAX_RESENDS": "3",
    "OTP_MAX_ATTEMPTS": "5",
    "RESET_CODE_TTL_SECONDS": "900",
    "PIN_MAX_FAILURES": "3",
    "PASSWORD_MAX_FAILURES": "3",
    "PASSWORD_LOCKOUT_SECONDS": "300",
    "PASSWORD_LOCKOUT_EXTENDED_SECONDS": "3600",
    "PAYMENT_PER_TRANSACTION_LIMIT_MINOR": "2000000",
    "PAYMENT_DAILY_LIMIT_MINOR": "10000000",
    "PAYMENT_STEP_UP_THRESHOLD_MINOR": "50000",
    "STEP_UP_CODE_TTL_SECONDS": "300",
    "STEP_UP_MAX_ATTEMPTS": "3",
    "STEP_UP_DEV_CODE": "000000",
    "SESSION_TTL_SECONDS": "3600",
    "DEMO_OPENING_BALANCE_MINOR": "250000",
    "TRANSACTIONS_PAGE_SIZE": "25",
    "CASHFLOW_LOW_BALANCE_THRESHOLD_MINOR": "0",
}

for _name, _value in _TEST_ENV.items():
    os.environ[_name] = _value
