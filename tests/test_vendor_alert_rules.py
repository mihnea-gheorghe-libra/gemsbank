from typing import Any

from backend.vendors.detector import (
    ABSOLUTE_COHORT,
    CONFIRMED,
    PERSONAL_INCREASE,
    PREDICTIVE,
    ROLLING,
    YEAR_OVER_YEAR,
    DetectorConfig,
    detect,
    personal_increase_cohort,
)

CONFIG = DetectorConfig(source_collection="unit")
PERSONAL_ONLY = DetectorConfig(source_collection="unit", use_absolute_cohort=False)
ABSOLUTE_ONLY = DetectorConfig(source_collection="unit", use_personal_increase=False)


def month(label: str, median: int, users: int = 10) -> dict[str, Any]:
    return {
        "vendorNormalized": "ACME",
        "currency": "RON",
        "month": label,
        "medianMinorUnits": median,
        "minMinorUnits": median,
        "maxMinorUnits": median,
        "uniqueUserCount": users,
    }


def cohort(amount: int, users: int) -> dict[str, Any]:
    return {
        "amountMinorUnits": amount,
        "userCount": users,
        "transactionCount": users,
    }


def series(*months: dict[str, Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    return {("ACME", "RON"): list(months)}


def user_months(
    user_id: str, prices: dict[str, int]
) -> tuple[tuple[str, str, str], list[dict[str, Any]]]:
    return (
        ("ACME", "RON", user_id),
        [
            {"month": label, "priceMinorUnits": price, "transactionCount": 1}
            for label, price in sorted(prices.items())
        ],
    )


def users(*entries: tuple[tuple[str, str, str], list[dict[str, Any]]]) -> dict[
    tuple[str, str, str], list[dict[str, Any]]
]:
    return dict(entries)


def types_by_month(alerts: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {(alert["month"], alert["alertType"]) for alert in alerts}


def test_a_vendor_with_less_than_three_prior_months_never_alerts() -> None:
    stats = series(month("2026-01", 4900), month("2026-02", 4900), month("2026-03", 9900))
    cohorts = {("ACME", "RON", "2026-03"): [cohort(9900, 5)]}

    alerts, skipped = detect(stats, cohorts, {}, [], CONFIG)

    assert alerts == []
    assert all(row["reason"] == "insufficient_history" for row in skipped)


def test_a_confirmed_rise_is_announced_once_not_every_month_it_persists() -> None:
    stats = series(
        month("2026-02", 4900),
        month("2026-03", 4900),
        month("2026-04", 4900),
        month("2026-05", 4900),
        month("2026-06", 5900),
        month("2026-07", 5900),
    )

    alerts, skipped = detect(stats, {}, {}, [], CONFIG)

    confirmed = [alert for alert in alerts if alert["alertType"] == CONFIRMED]
    assert [alert["month"] for alert in confirmed] == ["2026-06"]
    assert any(row["reason"] == "already_confirmed" for row in skipped)


def test_a_second_distinct_rise_is_announced_again() -> None:
    stats = series(
        month("2026-02", 4900),
        month("2026-03", 4900),
        month("2026-04", 4900),
        month("2026-05", 5900),
        month("2026-06", 5900),
        month("2026-07", 5900),
        month("2026-08", 7900),
        month("2026-09", 7900),
    )

    alerts, _ = detect(stats, {}, {}, [], CONFIG)

    confirmed = [alert["month"] for alert in alerts if alert["alertType"] == CONFIRMED]
    assert confirmed == ["2026-05", "2026-08"]


def test_predictive_and_confirmed_can_both_fire_for_the_same_month() -> None:
    stats = series(
        month("2026-02", 10000),
        month("2026-03", 10000),
        month("2026-04", 10000),
        month("2026-05", 12000),
    )
    cohorts = {("ACME", "RON", "2026-05"): [cohort(12000, 6), cohort(13000, 3)]}

    alerts, _ = detect(stats, cohorts, {}, [], ABSOLUTE_ONLY)

    assert types_by_month(alerts) == {("2026-05", PREDICTIVE), ("2026-05", CONFIRMED)}


def test_a_price_already_present_in_the_baseline_window_is_not_predictive() -> None:
    stats = series(
        month("2026-02", 4900),
        month("2026-03", 4900),
        month("2026-04", 4900),
        month("2026-05", 4900),
    )
    cohorts = {
        ("ACME", "RON", "2026-03"): [cohort(4900, 9), cohort(5900, 1)],
        ("ACME", "RON", "2026-04"): [cohort(4900, 9), cohort(5900, 2)],
        ("ACME", "RON", "2026-05"): [cohort(4900, 7), cohort(5900, 4)],
    }

    alerts, _ = detect(stats, cohorts, {}, [], ABSOLUTE_ONLY)

    assert alerts == []


def test_a_new_price_below_the_predictive_threshold_is_noise_not_a_signal() -> None:
    stats = series(
        month("2026-02", 27000),
        month("2026-03", 27000),
        month("2026-04", 27000),
        month("2026-05", 27000),
    )
    cohorts = {("ACME", "RON", "2026-05"): [cohort(28000, 4)]}

    alerts, _ = detect(stats, cohorts, {}, [], CONFIG)

    assert alerts == []


def test_an_existing_alert_on_record_suppresses_a_rerun_duplicate() -> None:
    stats = series(
        month("2026-02", 4900),
        month("2026-03", 4900),
        month("2026-04", 4900),
        month("2026-05", 5900),
    )
    existing = [
        {
            "vendor": "ACME",
            "currency": "RON",
            "alertType": CONFIRMED,
            "baselineMinorUnits": 4900,
            "observedMinorUnits": 5900,
        }
    ]

    alerts, skipped = detect(stats, {}, {}, existing, CONFIG)

    assert alerts == []
    assert any(row["reason"] == "already_confirmed" for row in skipped)


def test_a_rise_split_across_users_with_different_amounts_is_still_predictive() -> None:
    stats = series(
        month("2026-04", 18500, users=3),
        month("2026-05", 18500, users=3),
        month("2026-06", 18500, users=3),
        month("2026-07", 19000, users=3),
    )
    people = users(
        user_months("u1", {"2026-04": 18000, "2026-05": 18000, "2026-06": 18000, "2026-07": 20700}),
        user_months("u2", {"2026-04": 18500, "2026-05": 18500, "2026-06": 18500, "2026-07": 21300}),
        user_months("u3", {"2026-04": 19000, "2026-05": 19000, "2026-06": 19000, "2026-07": 19100}),
    )

    absolute_alerts, _ = detect(stats, {}, people, [], ABSOLUTE_ONLY)
    personal_alerts, _ = detect(stats, {}, people, [], PERSONAL_ONLY)

    assert absolute_alerts == []
    assert [alert["month"] for alert in personal_alerts] == ["2026-07"]
    assert personal_alerts[0]["alertType"] == PREDICTIVE
    assert personal_alerts[0]["signalMechanisms"] == [PERSONAL_INCREASE]
    assert personal_alerts[0]["observedUserCount"] == 2
    assert personal_alerts[0]["eligibleUserCount"] == 3


def test_at_a_fixed_price_both_mechanisms_agree() -> None:
    stats = series(
        month("2026-02", 4900, users=3),
        month("2026-03", 4900, users=3),
        month("2026-04", 4900, users=3),
        month("2026-05", 4900, users=3),
    )
    cohorts = {
        ("ACME", "RON", "2026-02"): [cohort(4900, 3)],
        ("ACME", "RON", "2026-03"): [cohort(4900, 3)],
        ("ACME", "RON", "2026-04"): [cohort(4900, 3)],
        ("ACME", "RON", "2026-05"): [cohort(4900, 1), cohort(5900, 2)],
    }
    people = users(
        user_months("u1", {"2026-02": 4900, "2026-03": 4900, "2026-04": 4900, "2026-05": 5900}),
        user_months("u2", {"2026-02": 4900, "2026-03": 4900, "2026-04": 4900, "2026-05": 5900}),
        user_months("u3", {"2026-02": 4900, "2026-03": 4900, "2026-04": 4900, "2026-05": 4900}),
    )

    alerts, _ = detect(stats, cohorts, people, [], CONFIG)

    assert len(alerts) == 1
    assert alerts[0]["signalMechanisms"] == [PERSONAL_INCREASE, ABSOLUTE_COHORT]
    assert alerts[0]["baselineMinorUnits"] == 4900
    assert alerts[0]["observedMinorUnits"] == 5900


def test_a_user_without_three_months_of_own_history_is_skipped_not_counted() -> None:
    stats = series(
        month("2026-02", 4900, users=3),
        month("2026-03", 4900, users=3),
        month("2026-04", 4900, users=3),
        month("2026-05", 4900, users=3),
    )
    people = users(
        user_months("veteran", {"2026-02": 4900, "2026-03": 4900, "2026-04": 4900, "2026-05": 5900}),
        user_months("newcomer_a", {"2026-04": 4900, "2026-05": 5900}),
        user_months("newcomer_b", {"2026-04": 4900, "2026-05": 5900}),
    )

    alerts, _ = detect(stats, {}, people, [], PERSONAL_ONLY)

    assert alerts == []


def test_a_staggered_rollout_is_announced_once_not_as_each_wave_lands() -> None:
    stats = series(
        month("2026-02", 4900, users=2),
        month("2026-03", 4900, users=2),
        month("2026-04", 4900, users=2),
        month("2026-05", 4900, users=2),
        month("2026-06", 5900, users=2),
        month("2026-07", 5900, users=2),
    )
    people = users(
        user_months("early_a", {"2026-02": 4900, "2026-03": 4900, "2026-04": 4900, "2026-05": 5900, "2026-06": 5900, "2026-07": 5900}),
        user_months("early_b", {"2026-02": 4900, "2026-03": 4900, "2026-04": 4900, "2026-05": 5900, "2026-06": 5900, "2026-07": 5900}),
        user_months("late_a", {"2026-02": 4900, "2026-03": 4900, "2026-04": 4900, "2026-05": 4900, "2026-06": 5900, "2026-07": 5900}),
        user_months("late_b", {"2026-02": 4900, "2026-03": 4900, "2026-04": 4900, "2026-05": 4900, "2026-06": 5900, "2026-07": 5900}),
    )

    alerts, skipped = detect(stats, {}, people, [], PERSONAL_ONLY)

    predictive = [alert["month"] for alert in alerts if alert["alertType"] == PREDICTIVE]
    assert predictive == ["2026-05"]
    assert any(row["reason"] == "already_predicted" for row in skipped)


def test_a_share_gate_can_reject_a_cohort_that_is_a_rounding_error_of_the_base() -> None:
    stats = series(
        month("2026-02", 18500, users=100),
        month("2026-03", 18500, users=100),
        month("2026-04", 18500, users=100),
        month("2026-05", 18500, users=100),
    )
    people = users(
        *[
            user_months(
                f"steady_{index}",
                {"2026-02": 18500, "2026-03": 18500, "2026-04": 18500, "2026-05": 18500},
            )
            for index in range(20)
        ],
        user_months("mover_a", {"2026-02": 18500, "2026-03": 18500, "2026-04": 18500, "2026-05": 21000}),
        user_months("mover_b", {"2026-02": 18500, "2026-03": 18500, "2026-04": 18500, "2026-05": 21000}),
    )

    without_gate, _ = detect(stats, {}, people, [], PERSONAL_ONLY)
    with_gate, _ = detect(
        stats,
        {},
        people,
        [],
        DetectorConfig(
            source_collection="unit",
            use_absolute_cohort=False,
            min_personal_increase_share=0.25,
        ),
    )

    assert [alert["month"] for alert in without_gate] == ["2026-05"]
    assert with_gate == []


SUMMER_TO_WINTER = {
    "2024-08": 18500,
    "2024-09": 19500,
    "2024-10": 21000,
    "2024-11": 23500,
    "2024-12": 24800,
    "2025-01": 25100,
    "2025-02": 24500,
    "2025-03": 23200,
    "2025-04": 21700,
    "2025-05": 20100,
    "2025-06": 18900,
    "2025-07": 18600,
    "2025-08": 18500,
    "2025-09": 19500,
    "2025-10": 21000,
    "2025-11": 23500,
}


def seasonal_stats() -> dict[tuple[str, str], list[dict[str, Any]]]:
    return series(
        *[month(label, price, users=4) for label, price in sorted(SUMMER_TO_WINTER.items())]
    )


def seasonal_users(count: int = 4) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    return users(
        *[user_months(f"u{index}", dict(SUMMER_TO_WINTER)) for index in range(count)]
    )


def test_a_seasonal_autumn_to_winter_climb_is_not_a_price_rise() -> None:
    alerts, _ = detect(seasonal_stats(), {}, seasonal_users(), [], PERSONAL_ONLY)

    winter_after_a_full_year = [
        alert for alert in alerts if alert["month"] >= "2025-08"
    ]
    assert winter_after_a_full_year == []


def test_the_same_climb_does_alert_while_no_year_of_history_exists_yet() -> None:
    alerts, _ = detect(seasonal_stats(), {}, seasonal_users(), [], PERSONAL_ONLY)

    cold_start = [alert for alert in alerts if alert["month"] < "2025-08"]
    assert cold_start != []
    assert all(alert["baselineMethod"] == ROLLING for alert in cold_start)


def test_a_real_rise_on_top_of_the_season_is_still_caught() -> None:
    prices = dict(SUMMER_TO_WINTER)
    raised = {**prices, "2025-11": round(prices["2025-11"] * 1.15)}
    stats = series(
        *[month(label, price, users=4) for label, price in sorted(raised.items())]
    )
    people = users(
        user_months("mover_a", raised),
        user_months("mover_b", raised),
        user_months("steady_a", prices),
        user_months("steady_b", prices),
    )

    alerts, _ = detect(stats, {}, people, [], PERSONAL_ONLY)

    hits = [
        alert
        for alert in alerts
        if alert["month"] == "2025-11" and alert["alertType"] == PREDICTIVE
    ]
    assert len(hits) == 1
    assert hits[0]["baselineMethod"] == YEAR_OVER_YEAR
    assert hits[0]["observedUserCount"] == 2


def test_a_user_without_a_year_of_history_falls_back_instead_of_being_dropped() -> None:
    veteran = dict(SUMMER_TO_WINTER)
    newcomer = {
        label: price for label, price in SUMMER_TO_WINTER.items() if label >= "2025-06"
    }
    stats = series(
        *[month(label, price, users=2) for label, price in sorted(SUMMER_TO_WINTER.items())]
    )
    people = users(
        user_months("veteran", veteran),
        user_months("newcomer", newcomer),
    )

    flagged, eligible = personal_increase_cohort(
        people, "ACME", "RON", "2025-11", PERSONAL_ONLY
    )

    assert eligible == 2
    methods = {row["userId"]: row["baselineMethod"] for row in flagged}
    assert methods.get("newcomer") == ROLLING
    assert "veteran" not in methods


def test_year_over_year_can_be_switched_off_and_the_old_behaviour_returns() -> None:
    config = DetectorConfig(
        source_collection="unit", use_absolute_cohort=False, use_year_over_year=False
    )

    alerts, _ = detect(seasonal_stats(), {}, seasonal_users(), [], config)

    late = [alert for alert in alerts if alert["month"] >= "2025-08"]
    assert late != []
