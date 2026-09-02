from backend.fx.signals import (
    BELOW_THRESHOLD,
    DOWN,
    NO_BASELINE,
    SIGNAL_UNIQUE_KEY,
    UP,
    SignalRule,
    build_signal,
    resolve_baseline,
)
from backend.fx.validation import percent_change

RULE = SignalRule()

EUR_HISTORY = {
    "2026-08-13": 5_150_000,
    "2026-08-17": 5_171_200,
    "2026-08-19": 5_180_000,
    "2026-08-25": 5_240_000,
}


def test_a_rate_that_did_not_move_produces_no_percentage() -> None:
    assert percent_change(5_258_900, 5_258_900) == 0.0


def test_the_percentage_is_measured_against_the_baseline_not_the_current_rate() -> None:
    assert round(percent_change(5_258_900, 5_171_200), 4) == 1.6959
    assert round(percent_change(5_171_200, 5_258_900), 4) == -1.6676


def test_a_missing_or_zero_baseline_never_divides_by_zero() -> None:
    assert percent_change(5_258_900, 0) == 0.0
    assert percent_change(5_258_900, -1) == 0.0


def test_the_baseline_is_the_last_published_day_at_or_before_the_window() -> None:
    resolved = resolve_baseline(EUR_HISTORY, "2026-08-26", 7)

    assert resolved == ("2026-08-19", 5_180_000)


def test_a_weekend_or_holiday_gap_falls_back_to_the_previous_banking_day() -> None:
    history = {"2026-08-13": 5_150_000, "2026-08-14": 5_160_000}

    resolved = resolve_baseline(history, "2026-08-24", 7)

    assert resolved == ("2026-08-14", 5_160_000)


def test_a_currency_without_enough_history_yields_no_signal_instead_of_a_guess() -> None:
    signal, reason = build_signal("EUR", "2026-08-26", 5_258_900, {}, RULE)

    assert signal is None
    assert reason == NO_BASELINE


def test_a_move_under_the_threshold_is_noise_and_stays_unreported() -> None:
    history = {"2026-08-19": 5_240_000}

    signal, reason = build_signal("EUR", "2026-08-26", 5_258_900, history, RULE)

    assert signal is None
    assert reason == BELOW_THRESHOLD


def test_a_move_over_the_threshold_becomes_an_up_signal() -> None:
    signal, reason = build_signal("EUR", "2026-08-26", 5_258_900, EUR_HISTORY, RULE)

    assert reason == ""
    assert signal is not None
    assert signal["direction"] == UP
    assert signal["currency"] == "EUR"
    assert signal["date"] == "2026-08-26"
    assert signal["baselineDate"] == "2026-08-19"
    assert signal["baselineRate"] == 5_180_000
    assert signal["currentRate"] == 5_258_900
    assert signal["changePercent"] == 1.5232
    assert signal["source"] == "bnr"


def test_a_fall_over_the_threshold_becomes_a_down_signal() -> None:
    history = {"2026-08-19": 5_400_000}

    signal, _ = build_signal("EUR", "2026-08-26", 5_258_900, history, RULE)

    assert signal is not None
    assert signal["direction"] == DOWN
    assert signal["changePercent"] < 0


def test_the_threshold_is_an_fx_sized_number_not_a_vendor_sized_one() -> None:
    assert RULE.threshold_percent == 0.5
    assert RULE.baseline_days == 7


def test_a_looser_threshold_lets_a_smaller_move_through() -> None:
    history = {"2026-08-19": 5_240_000}
    loose = SignalRule(threshold_percent=0.3)

    signal, _ = build_signal("EUR", "2026-08-26", 5_258_900, history, loose)

    assert signal is not None
    assert signal["thresholdPercent"] == 0.3


def test_a_signal_is_identified_by_source_currency_and_day_so_a_rerun_upserts() -> None:
    signal, _ = build_signal("EUR", "2026-08-26", 5_258_900, EUR_HISTORY, RULE)
    again, _ = build_signal("EUR", "2026-08-26", 5_258_900, EUR_HISTORY, RULE)

    assert signal is not None and again is not None
    assert SIGNAL_UNIQUE_KEY == ("source", "currency", "date")
    assert {field: signal[field] for field in SIGNAL_UNIQUE_KEY} == {
        field: again[field] for field in SIGNAL_UNIQUE_KEY
    }
    assert signal["signalKey"] == "bnr:EUR:2026-08-26"
