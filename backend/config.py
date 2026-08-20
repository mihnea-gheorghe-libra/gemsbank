from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongo_uri: str = "mongodb://localhost:27017/gems?replicaSet=rs0"
    mongo_db_name: str = "gems"

    resend_api_key: str | None = None
    otp_from_email: str = "onboarding@resend.dev"

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


settings = Settings()
