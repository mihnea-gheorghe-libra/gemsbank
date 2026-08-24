from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongo_uri: str = "mongodb://localhost:27017/gems?replicaSet=rs0"
    mongo_db_name: str = "gems"

    resend_api_key: str | None = None
    otp_from_email: str = "onboarding@resend.dev"

    azure_docintel_endpoint: str | None = None
    azure_docintel_key: str | None = None

    pin_encryption_key: str | None = None

    web_dir: str = str(_REPO_ROOT / "frontend")

    otp_ttl_seconds: int
    otp_resend_cooldown_seconds: int
    otp_max_resends: int
    otp_max_attempts: int

    reset_code_ttl_seconds: int

    minimum_age_years: int = 18

    pin_max_failures: int

    password_max_failures: int
    password_lockout_seconds: int
    password_lockout_extended_seconds: int

    session_ttl_seconds: int = 3600

    demo_opening_balance_minor: int = 250000

    payment_per_transaction_limit_minor: int = 2000000
    payment_daily_limit_minor: int = 5000000
    payment_step_up_threshold_minor: int = 100000
    step_up_code_ttl_seconds: int = 300
    step_up_max_attempts: int = 3
    step_up_dev_code: str = "000000"

    transactions_page_size: int = 25
    ocr_min_confidence: float = 0.60



settings = Settings()  # type: ignore[call-arg]

