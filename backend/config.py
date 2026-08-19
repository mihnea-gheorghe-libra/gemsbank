from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongo_uri: str = "mongodb://localhost:27017/gems?replicaSet=rs0"
    mongo_db_name: str = "gems"

    resend_api_key: str | None = None
    otp_from_email: str = "onboarding@resend.dev"

    web_dir: str = str(_REPO_ROOT / "frontend")

    otp_ttl_seconds: int = 300
    otp_resend_cooldown_seconds: int = 30
    otp_max_resends: int = 3
    otp_max_attempts: int = 5

    minimum_age_years: int = 18


settings = Settings()
