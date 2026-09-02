from typing import Any

from backend.vendors.decision_engine import (
    HIGH,
    LOW,
    NOTIFICATION_UNIQUE_KEY,
    PENDING,
    DecisionConfig,
    build_notifications,
    confidence_for,
    render_long,
    render_news_predictive_long,
    render_short,
    vendor_profiles,
)
from backend.vendors.detector import CONFIRMED, PREDICTIVE, ROLLING, YEAR_OVER_YEAR

CONFIG = DecisionConfig(source_collection="unit")
WITH_LOW = DecisionConfig(source_collection="unit", include_low_confidence=True)

NETFLIX_PROFILE = {
    ("NETFLIX", "RON"): {"displayName": "Netflix", "category": "entertainment"}
}


def alert(
    alert_type: str,
    baseline_method: str,
    vendor: str = "NETFLIX",
    month: str = "2026-05",
    percent: float = 0.204082,
) -> dict[str, Any]:
    return {
        "source": "unit",
        "vendor": vendor,
        "currency": "RON",
        "month": month,
        "alertType": alert_type,
        "baselineMethod": baseline_method,
        "percentChange": percent,
    }


def netflix_users(
    switched: int, total: int, month: str = "2026-05"
) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    history = ["2026-02", "2026-03", "2026-04"]
    people: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for index in range(total):
        price = 5900 if index < switched else 4900
        people[("NETFLIX", "RON", f"u{index}")] = [
            {"month": label, "priceMinorUnits": 4900} for label in history
        ] + [{"month": month, "priceMinorUnits": price}]
    return people


def test_a_year_old_baseline_is_trusted_whichever_signal_raised_it() -> None:
    assert confidence_for(alert(CONFIRMED, YEAR_OVER_YEAR)) == HIGH
    assert confidence_for(alert(PREDICTIVE, YEAR_OVER_YEAR)) == HIGH


def test_a_cold_start_baseline_is_distrusted_whichever_signal_raised_it() -> None:
    assert confidence_for(alert(CONFIRMED, ROLLING)) == LOW
    assert confidence_for(alert(PREDICTIVE, ROLLING)) == LOW


def test_the_seasonal_alert_that_slipped_through_is_low_on_both_signals() -> None:
    seasonal = {
        "predictive": alert(PREDICTIVE, ROLLING, vendor="ENEL ENERGIE", month="2024-11", percent=0.165432),
        "confirmed": alert(CONFIRMED, ROLLING, vendor="ENEL ENERGIE", month="2024-11", percent=0.165432),
    }

    assert confidence_for(seasonal["predictive"]) == LOW
    assert confidence_for(seasonal["confirmed"]) == LOW

    notifications, skipped = build_notifications(
        list(seasonal.values()), NETFLIX_PROFILE, netflix_users(15, 15, month="2024-11"), CONFIG
    )

    assert notifications == []
    assert [row["reason"] for row in skipped] == [
        "low_confidence_suppressed",
        "low_confidence_suppressed",
    ]


def test_confidence_no_longer_depends_on_the_alert_type_at_all() -> None:
    for method in (YEAR_OVER_YEAR, ROLLING):
        assert confidence_for(alert(CONFIRMED, method)) == confidence_for(
            alert(PREDICTIVE, method)
        )


def test_low_confidence_produces_no_notification_by_default() -> None:
    alerts = [alert(PREDICTIVE, ROLLING)]

    notifications, skipped = build_notifications(
        alerts, NETFLIX_PROFILE, netflix_users(3, 15), CONFIG
    )

    assert notifications == []
    assert [row["reason"] for row in skipped] == ["low_confidence_suppressed"]


def test_low_confidence_can_be_kept_and_is_marked_as_such() -> None:
    alerts = [alert(PREDICTIVE, ROLLING)]

    notifications, _ = build_notifications(
        alerts, NETFLIX_PROFILE, netflix_users(3, 15), WITH_LOW
    )

    assert len(notifications) == 3
    assert {row["confidence"] for row in notifications} == {LOW}
    assert all("ar putea" in row["longText"] for row in notifications)


def test_the_known_netflix_rise_renders_a_short_and_a_long_text() -> None:
    alerts = [alert(PREDICTIVE, YEAR_OVER_YEAR)]

    notifications, _ = build_notifications(
        alerts, NETFLIX_PROFILE, netflix_users(3, 15), CONFIG
    )

    assert len(notifications) == 3
    first = notifications[0]
    assert first["shortText"] == "Netflix +20%"
    assert first["longText"] == (
        "Abonamentul tău la Netflix s-a scumpit cu 20% "
        "(de la {baseline} la {observed})"
    )
    assert first["baselineMinorUnits"] == 4900
    assert first["observedMinorUnits"] == 5900
    assert first["currency"] == "RON"
    assert len(first["shortText"]) < 60
    assert first["status"] == PENDING
    assert first["confidence"] == HIGH


def test_only_users_whose_own_price_moved_are_notified() -> None:
    alerts = [alert(CONFIRMED, YEAR_OVER_YEAR)]

    notifications, _ = build_notifications(
        alerts, NETFLIX_PROFILE, netflix_users(9, 15), CONFIG
    )

    assert len(notifications) == 9
    assert {row["observedMinorUnits"] for row in notifications} == {5900}


def test_the_same_run_twice_produces_the_same_notification_keys() -> None:
    alerts = [alert(CONFIRMED, YEAR_OVER_YEAR)]
    people = netflix_users(9, 15)

    first, _ = build_notifications(alerts, NETFLIX_PROFILE, people, CONFIG)
    second, _ = build_notifications(alerts, NETFLIX_PROFILE, people, CONFIG)

    keys = [tuple(row[field] for field in NOTIFICATION_UNIQUE_KEY) for row in first]
    assert keys == [
        tuple(row[field] for field in NOTIFICATION_UNIQUE_KEY) for row in second
    ]
    assert len(set(keys)) == len(keys)


def test_the_wording_follows_the_category_not_the_vendor_name() -> None:
    bill = render_long("Enel Energie", "utilities", HIGH, 0.15, 18500, 21275, "RON")
    subscription = render_long("Netflix", "entertainment", HIGH, 0.15, 4900, 5635, "RON")
    unknown = render_long("Ceva Nou", "", HIGH, 0.15, 1000, 1150, "RON")

    assert bill.startswith("Factura ta la Enel Energie")
    assert subscription.startswith("Abonamentul tău la Netflix")
    assert unknown.startswith("Plățile tale la Ceva Nou")


def test_a_long_vendor_name_still_fits_the_small_card() -> None:
    text = render_short("A" * 120, 0.204082)

    assert len(text) <= 60
    assert text.endswith("+20%")


def test_the_display_name_is_the_most_common_raw_spelling() -> None:
    rows = [
        {
            "vendorNormalized": "KAUFLAND BANEASA",
            "currency": "RON",
            "counterpartyVariants": ["Kaufland Băneasa"],
            "categories": ["groceries"],
        },
        {
            "vendorNormalized": "KAUFLAND BANEASA",
            "currency": "RON",
            "counterpartyVariants": ["Kaufland Băneasa"],
            "categories": ["groceries"],
        },
        {
            "vendorNormalized": "KAUFLAND BANEASA",
            "currency": "RON",
            "counterpartyVariants": ["KAUFLAND BANEASA"],
            "categories": ["groceries"],
        },
    ]

    profiles = vendor_profiles(rows)

    assert profiles[("KAUFLAND BANEASA", "RON")]["displayName"] == "Kaufland Băneasa"
    assert profiles[("KAUFLAND BANEASA", "RON")]["category"] == "groceries"


def test_an_alert_nobody_actually_felt_produces_nothing() -> None:
    alerts = [alert(CONFIRMED, YEAR_OVER_YEAR)]

    notifications, skipped = build_notifications(
        alerts, NETFLIX_PROFILE, netflix_users(0, 15), CONFIG
    )

    assert notifications == []
    assert [row["reason"] for row in skipped] == ["no_user_moved"]


def test_the_wording_leaves_money_formatting_to_the_client() -> None:
    internal = render_long("Enel Energie", "utilities", HIGH, 0.15, 184886, 212619, "RON")
    announced = render_news_predictive_long(
        "Enel Energie",
        "utilities",
        {"publishers": ["Adevarul.ro"], "effectiveDate": "2026-07-01"},
        184886,
        "RON",
    )

    for text in (internal, announced):
        assert "1848.86" not in text
        assert "1,848.86" not in text
    assert "{baseline}" in internal and "{observed}" in internal
    assert "{baseline}" in announced
