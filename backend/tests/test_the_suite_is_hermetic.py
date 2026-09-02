from pathlib import Path

from backend.config import settings


def test_settings_come_from_the_test_environment_not_a_developers_dotenv() -> None:
    assert settings.payment_per_transaction_limit_minor == 2000000
    assert settings.payment_daily_limit_minor == 10000000
    assert settings.payment_step_up_threshold_minor == 50000
    assert settings.pin_max_failures == 3


def test_web_dir_resolves_to_a_real_frontend_whatever_the_working_directory() -> None:
    assert (Path(settings.web_dir) / "help.html").is_file()


def test_the_faq_capability_can_read_its_source_document() -> None:
    from backend.capabilities.support_docs import search_support_docs

    assert search_support_docs("") != []
