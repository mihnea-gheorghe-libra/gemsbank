from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
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

    gnews_api_key: str | None = None
    gnews_base_url: str = "https://gnews.io/api/v4"
    gnews_min_request_interval_seconds: float = 1.1

    vendor_insights_source: str = "payments_seed_demo"
    vendor_insights_limit: int = 3

    bnr_fx_feed_url: str = "https://curs.bnr.ro/nbrfxrates.xml"
    bnr_fx_history_feed_url: str = "https://curs.bnr.ro/nbrfxrates10days.xml"
    bnr_fx_source_page_url: str = (
        "https://www.bnr.ro/23988-cursurile-pietei-valutare-in-format-xml"
    )
    fx_signal_threshold_percent: float = 1.5
    fx_baseline_days: int = 7
    fx_repeat_rate_tolerance_percent: float = 0.5
    fx_insights_source: str = "bnr"
    fx_insights_limit: int = 3

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

<<<<<<< HEAD
    agent_rate_limit_max_calls: int = 20
    agent_rate_limit_window_seconds: int = 3600
=======
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_deployment: str | None = Field(
        default=None,
        validation_alias=AliasChoices("azure_openai_deployment", "azure_openai_deployment_name"),
    )
    azure_openai_deployment_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("azure_openai_deployment_name", "azure_openai_deployment"),
    )

    @model_validator(mode="after")
    def _sync_azure_openai_fields(self) -> "Settings":
        if not self.azure_openai_deployment and self.azure_openai_deployment_name:
            object.__setattr__(self, "azure_openai_deployment", self.azure_openai_deployment_name)
        elif not self.azure_openai_deployment_name and self.azure_openai_deployment:
            object.__setattr__(self, "azure_openai_deployment_name", self.azure_openai_deployment)
        return self

    azure_speech_endpoint: str | None = None
    azure_speech_api_key: str | None = None
    azure_speech_region: str | None = None
    azure_speech_api_version: str = "2024-11-15"
    speech_max_upload_bytes: int = 12_000_000
    speech_timeout_seconds: float = 30.0
    speech_tts_max_chars: int = 5000
    azure_speech_tts_voice_ro: str = "ro-RO-AlinaNeural"
    azure_speech_tts_voice_en: str = "en-US-JennyNeural"
>>>>>>> f246952780604fd79494ff16c6ba4db93b0d52b8

    cashflow_low_balance_threshold_minor: int = 0

    standing_orders_poll_seconds: int = 3600

    yahoo_chart_base_url: str = "https://query1.finance.yahoo.com"
    frankfurter_base_url: str = "https://api.frankfurter.app"
    investments_timeout_seconds: float = 6.0
    investments_quote_ttl_seconds: int = 900
    investments_retry_seconds: int = 60
    investments_min_refresh_seconds: int = 3
    investments_series_days: int = 400



settings = Settings()  # type: ignore[call-arg]

