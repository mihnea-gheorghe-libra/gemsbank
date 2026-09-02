import math
from datetime import UTC, datetime
from typing import Any

from backend.vendors.decision_engine import (
    COLD_START_UNBLOCKED_BY_NEWS,
    DUAL_CORROBORATED,
    EXTERNAL_NEWS_PREDICTIVE,
    HIGH,
    INTERNAL_MATHEMATICAL,
    LOW,
    MEDIUM,
    NOTIFICATION_UNIQUE_KEY,
    PENDING,
    SAME_NEWS_EPISODE,
    SAME_PRICE_STATE,
    DecisionConfig,
    build_notifications,
    evaluate_internal_alert,
    news_matches_alert,
    news_matches_vendor,
    news_episodes,
)
from backend.vendors.detector import CONFIRMED, PREDICTIVE, ROLLING, YEAR_OVER_YEAR

CONFIG = DecisionConfig(source_collection="unit")

PROFILES = {
    ("NETFLIX", "RON"): {"displayName": "Netflix", "category": "entertainment"},
    ("DIGI COMMUNICATIONS", "RON"): {
        "displayName": "Digi",
        "category": "utilities",
    },
    ("ENEL ENERGIE", "RON"): {
        "displayName": "Enel Energie",
        "category": "utilities",
    },
}


def internal_alert(
    vendor: str,
    month: str,
    alert_type: str = CONFIRMED,
    baseline_method: str = YEAR_OVER_YEAR,
    percent: float = 0.20,
    currency: str = "RON",
) -> dict[str, Any]:
    return {
        "source": "unit",
        "vendor": vendor,
        "currency": currency,
        "month": month,
        "alertType": alert_type,
        "baselineMethod": baseline_method,
        "percentChange": percent,
    }


def news_event(
    vendor: str,
    publishers: list[str],
    effective: str | None = None,
    market: str | None = "RO",
    percent: float | None = 20.0,
    confidence: str = HIGH,
    published_date: str = "2026-05-31T10:00:00",
) -> dict[str, Any]:
    return {
        "source": "newsSignals",
        "eventKey": f"event_{vendor}_{market}_{effective}_{'_'.join(publishers)}",
        "vendorNormalized": vendor,
        "vendorDisplayName": vendor.title(),
        "percentIncrease": percent,
        "effectiveDate": effective,
        "market": market,
        "confidence": confidence,
        "confidenceRule": "single_signal" if len(publishers) == 1 else "independent_corroboration",
        "publishers": publishers,
        "urls": [f"https://news.example/{p}" for p in publishers],
        "firstPublishedAt": datetime.fromisoformat(published_date).replace(tzinfo=UTC),
        "lastPublishedAt": datetime.fromisoformat(published_date).replace(tzinfo=UTC),
    }


def make_users(
    vendor: str, count: int, old_price: int = 4900, new_price: int = 5900, month: str = "2026-05"
) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    y, m = int(month[:4]), int(month[5:7])
    history = []
    for delta in range(3, 0, -1):
        tot = y * 12 + (m - 1) - delta
        history.append(f"{tot // 12:04d}-{tot % 12 + 1:02d}")

    people: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for i in range(count):
        people[(vendor, "RON", f"user_{i}")] = [
            {"month": past_m, "priceMinorUnits": old_price} for past_m in history
        ] + [{"month": month, "priceMinorUnits": new_price}]
    return people


def test_dual_corroboration_reinforces_alert_with_press_source() -> None:
    alerts = [internal_alert("NETFLIX", "2026-05", alert_type=CONFIRMED, baseline_method=YEAR_OVER_YEAR)]
    events = [news_event("NETFLIX", ["The Guardian", "Irish Examiner"], effective="2026-05-01", market="RO")]
    users = make_users("NETFLIX", 5, month="2026-05")

    notifs, skipped = build_notifications(alerts, PROFILES, users, CONFIG, news_events=events)

    assert len(notifs) == 5
    assert [row["reason"] for row in skipped] == [SAME_NEWS_EPISODE]
    for n in notifs:
        assert n["confidence"] == HIGH
        assert n["origin"] == DUAL_CORROBORATED
        assert "confirmat în presă (The Guardian, Irish Examiner)" in n["longText"]
        assert n["newsPublishers"] == ["The Guardian", "Irish Examiner"]
        assert n["newsEventKey"].startswith("event_NETFLIX_RO_2026-05-01")


def test_internal_mathematical_only_routes_to_confirmed_alert() -> None:
    alerts = [internal_alert("NETFLIX", "2026-05", alert_type=CONFIRMED, baseline_method=YEAR_OVER_YEAR)]
    users = make_users("NETFLIX", 3, month="2026-05")

    notifs, skipped = build_notifications(alerts, PROFILES, users, CONFIG, news_events=[])

    assert len(notifs) == 3
    assert skipped == []
    for n in notifs:
        assert n["confidence"] == HIGH
        assert n["origin"] == INTERNAL_MATHEMATICAL
        assert "confirmat în presă" not in n["longText"]
        assert n["newsEventKey"] is None


def test_cold_start_alert_is_unblocked_by_external_news() -> None:
    # A vendor in cold start (< 12 months) has rolling_3_month baseline
    alerts = [internal_alert("DIGI COMMUNICATIONS", "2024-11", alert_type=PREDICTIVE, baseline_method=ROLLING, percent=0.15)]
    events = [news_event("DIGI COMMUNICATIONS", ["Adevarul.ro"], effective="2024-11-01", market="RO", percent=15.0)]
    users = make_users("DIGI COMMUNICATIONS", 4, old_price=4000, new_price=4600, month="2024-11")

    # Without news, this alert would be suppressed due to cold start
    notifs_no_news, skipped_no_news = build_notifications(alerts, PROFILES, users, CONFIG, news_events=[])
    assert notifs_no_news == []
    assert len(skipped_no_news) == 1
    assert skipped_no_news[0]["reason"] == "low_confidence_suppressed"

    # With external news, cold start is unblocked!
    notifs, skipped = build_notifications(alerts, PROFILES, users, CONFIG, news_events=events)
    assert len(notifs) == 4
    assert [row["reason"] for row in skipped] == [SAME_NEWS_EPISODE]
    for n in notifs:
        assert n["confidence"] == HIGH
        assert n["origin"] == COLD_START_UNBLOCKED_BY_NEWS
        assert "confirmat în presă (Adevarul.ro)" in n["longText"]


def test_seasonal_false_positive_remains_suppressed_without_news() -> None:
    # Enel winter heating spike in November with rolling_3_month baseline
    seasonal_alerts = [internal_alert("ENEL ENERGIE", "2024-11", alert_type=CONFIRMED, baseline_method=ROLLING, percent=0.165)]
    # News for Enel is for Italy (market IT), NOT Romania
    italy_events = [news_event("ENEL ENERGIE", ["Reuters"], market="IT", effective=None)]
    users = make_users("ENEL ENERGIE", 5, old_price=20000, new_price=23300, month="2024-11")

    notifs, skipped = build_notifications(seasonal_alerts, PROFILES, users, CONFIG, news_events=italy_events)

    # Must remain suppressed!
    assert notifs == []
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "low_confidence_suppressed"


def test_predictive_alert_push_from_press_for_upcoming_increase() -> None:
    # Digi announces a price increase on 2026-05-31 effective 2026-07-01
    events = [
        news_event(
            "DIGI COMMUNICATIONS",
            ["Adevarul.ro"],
            effective="2026-07-01",
            market="RO",
            percent=10.0,
            confidence=HIGH,
        )
    ]
    # Existing subscribers paying Digi in previous months (2026-04, 2026-05)
    users = {
        ("DIGI COMMUNICATIONS", "RON", "user_1"): [
            {"month": "2026-04", "priceMinorUnits": 4500},
            {"month": "2026-05", "priceMinorUnits": 4500},
        ],
        ("DIGI COMMUNICATIONS", "RON", "user_2"): [
            {"month": "2026-04", "priceMinorUnits": 5000},
            {"month": "2026-05", "priceMinorUnits": 5000},
        ],
    }

    notifs, skipped = build_notifications([], PROFILES, users, CONFIG, news_events=events)

    assert len(notifs) == 2
    assert {n["userId"] for n in notifs} == {"user_1", "user_2"}
    for n in notifs:
        assert n["alertType"] == PREDICTIVE
        assert n["origin"] == EXTERNAL_NEWS_PREDICTIVE
        assert n["month"] == "2026-07"
        assert n["confidence"] == HIGH
        assert n["shortText"] == "Digi +10% (anunțat)"
        assert "Digi a anunțat o majorare de preț (cu ~10%, din 2026-07-01), conform relatărilor din presă (Adevarul.ro)" in n["longText"]


def test_foreign_market_news_does_not_trigger_romanian_notifications() -> None:
    morocco_event = news_event("NETFLIX", ["Morocco World News"], effective="2026-09-02", market="MA", percent=15.0)
    users = {
        ("NETFLIX", "RON", "user_ro"): [
            {"month": "2026-05", "priceMinorUnits": 4900}
        ]
    }

    assert news_matches_vendor(morocco_event, "NETFLIX", "RON") is False
    notifs, _ = build_notifications([], PROFILES, users, CONFIG, news_events=[morocco_event])
    assert notifs == []


def test_idempotent_notification_generation() -> None:
    alerts = [internal_alert("NETFLIX", "2026-05", alert_type=CONFIRMED, baseline_method=YEAR_OVER_YEAR)]
    events = [news_event("NETFLIX", ["The Guardian"], effective="2026-05-01", market="RO")]
    users = make_users("NETFLIX", 3, month="2026-05")

    first_notifs, _ = build_notifications(alerts, PROFILES, users, CONFIG, news_events=events)
    second_notifs, _ = build_notifications(alerts, PROFILES, users, CONFIG, news_events=events)

    keys_first = [tuple(n[k] for k in NOTIFICATION_UNIQUE_KEY) for n in first_notifs]
    keys_second = [tuple(n[k] for k in NOTIFICATION_UNIQUE_KEY) for n in second_notifs]

    assert keys_first == keys_second
    assert len(keys_first) == 3




def seasonal_price(month: str) -> int:
    calendar_month = int(month[5:7])
    swing = 1.0 + 0.35 * (1.0 + math.cos(2 * math.pi * (calendar_month - 1) / 12)) / 2
    return round(18500 * swing)


def year_of(year: int, last_month: int = 12) -> list[str]:
    return [f"{year}-{m:02d}" for m in range(1, last_month + 1)]


def series(prices: dict[str, int], vendor: str = "ENEL ENERGIE") -> dict:
    return {
        (vendor, "RON", "user_0"): [
            {"month": month, "priceMinorUnits": price}
            for month, price in sorted(prices.items())
        ]
    }


def flat_history(before: int, after: int) -> dict[str, int]:
    prices = {month: before for month in year_of(2025)}
    prices.update({month: after for month in year_of(2026, 7)})
    return prices


def seasonal_history(factor: float) -> dict[str, int]:
    prices = {month: seasonal_price(month) for month in year_of(2025)}
    prices.update(
        {month: round(seasonal_price(month) * factor) for month in year_of(2026, 7)}
    )
    return prices


def test_one_persistent_rise_is_notified_once_however_many_months_reconfirm_it() -> None:
    alerts = [
        internal_alert("ENEL ENERGIE", month, alert_type=kind, percent=0.22)
        for month in year_of(2026, 7)[3:]
        for kind in (CONFIRMED, PREDICTIVE)
    ]

    notifs, skipped = build_notifications(
        alerts, PROFILES, series(flat_history(20000, 24400)), CONFIG
    )

    assert len(notifs) == 1
    assert notifs[0]["month"] == "2026-04"
    assert notifs[0]["alertType"] == CONFIRMED
    assert {row["reason"] for row in skipped} == {SAME_PRICE_STATE}
    assert len(skipped) == 7


def test_a_seasonal_vendor_is_not_renotified_although_its_price_keeps_moving() -> None:
    prices = seasonal_history(1.22)
    alerts = [
        internal_alert("ENEL ENERGIE", month, percent=0.22)
        for month in year_of(2026, 7)[3:]
    ]

    notifs, skipped = build_notifications(alerts, PROFILES, series(prices), CONFIG)

    observed = [prices[month] for month in year_of(2026, 7)[3:]]
    assert max(observed) - min(observed) > 3900
    assert len(notifs) == 1
    assert {row["reason"] for row in skipped} == {SAME_PRICE_STATE}


def test_a_second_genuine_rise_still_reaches_the_user() -> None:
    prices = seasonal_history(1.22)
    for month in ("2026-06", "2026-07"):
        prices[month] = round(seasonal_price(month) * 1.85)
    alerts = [
        internal_alert("ENEL ENERGIE", month, percent=0.22)
        for month in year_of(2026, 7)[3:]
    ]

    notifs, _ = build_notifications(alerts, PROFILES, series(prices), CONFIG)

    months = [row["month"] for row in notifs]
    assert len(notifs) == 2
    assert months[0] == "2026-04"
    assert months[1] == "2026-06"


def test_later_articles_about_one_announcement_add_sources_not_rows() -> None:
    events = [
        news_event("NETFLIX", ["thestreet.com"], effective=None, market=None,
                   percent=None, published_date="2026-05-13T07:00:00"),
        news_event("NETFLIX", ["Washington Times"], effective=None, market=None,
                   percent=None, published_date="2026-06-15T07:00:00"),
        news_event("NETFLIX", ["Irish Examiner", "The Guardian"], effective=None,
                   market=None, percent=None, published_date="2026-08-24T13:45:00"),
    ]
    users = make_users("NETFLIX", 1, month="2026-05")

    notifs, skipped = build_notifications([], PROFILES, users, CONFIG, news_events=events)

    assert len(notifs) == 1
    assert notifs[0]["newsPublishers"] == [
        "thestreet.com", "Washington Times", "Irish Examiner", "The Guardian"
    ]
    assert [row["reason"] for row in skipped] == [SAME_NEWS_EPISODE] * 2


def test_an_announcement_for_another_market_stays_a_separate_episode() -> None:
    events = [
        news_event("NETFLIX", ["The Guardian"], effective=None, market=None,
                   percent=None, published_date="2026-08-24T13:45:00"),
        news_event("NETFLIX", ["Morocco World News"], effective="2026-09-02",
                   market="MA", percent=None, published_date="2026-08-06T07:00:00"),
    ]

    episode_of, publishers, _ = news_episodes(events, CONFIG)

    assert len(set(episode_of.values())) == 2
    grouped = sorted(sorted(names) for names in publishers.values())
    assert grouped == [["Morocco World News"], ["The Guardian"]]


def test_the_raw_event_history_is_never_touched_by_the_dedupe() -> None:
    events = [
        news_event("NETFLIX", ["thestreet.com"], effective=None, market=None,
                   percent=None, published_date="2026-05-13T07:00:00"),
        news_event("NETFLIX", ["Yahoo Tech"], effective=None, market=None,
                   percent=None, published_date="2026-07-08T07:00:00"),
    ]
    before = [dict(event) for event in events]
    users = make_users("NETFLIX", 1, month="2026-05")

    build_notifications([], PROFILES, users, CONFIG, news_events=events)

    assert events == before
