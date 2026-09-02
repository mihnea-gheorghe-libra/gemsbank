from datetime import UTC, datetime
from typing import Any

from backend.vendors.news_events import (
    DIFFERENT_EFFECTIVE_DATE,
    DIFFERENT_MARKET,
    DIFFERENT_VENDOR,
    INDEPENDENT_CORROBORATION,
    PERCENT_TOO_FAR_APART,
    PUBLISHED_TOO_FAR_APART,
    REPEAT_COVERAGE_SAME_ANNOUNCEMENT,
    SINGLE_SIGNAL,
    EventsConfig,
    build_event,
    group_signals,
    rejection_reasons,
    same_event,
)

CONFIG = EventsConfig(source_collection="unit")


def signal(
    publisher: str,
    published: str,
    vendor: str = "NETFLIX",
    effective: str | None = None,
    market: str | None = None,
    percent: float | None = None,
    confidence: str = "medium",
) -> dict[str, Any]:
    return {
        "vendorNormalized": vendor,
        "vendorDisplayName": vendor.title(),
        "articleUrl": f"https://news.example/{vendor}/{publisher}/{published}",
        "publisher": publisher,
        "publishedAt": datetime.fromisoformat(published).replace(tzinfo=UTC),
        "foundAt": datetime(2026, 8, 26, tzinfo=UTC),
        "effectiveDate": effective,
        "market": market,
        "percentIncrease": percent,
        "confidence": confidence,
        "summary": f"{publisher} on {vendor}",
        "sourceApi": "google_news",
        "language": "en",
    }


IRISH_EXAMINER = signal("Irish Examiner", "2026-08-24T15:45:00")
GUARDIAN = signal("The Guardian", "2026-08-24T13:45:00")
MOROCCO = signal(
    "Morocco World News",
    "2026-08-06T07:00:00",
    effective="2026-09-02",
    market="MA",
    confidence="high",
)


def keys(groups: list[list[dict[str, Any]]]) -> list[set[str]]:
    return [{row["publisher"] for row in group} for group in groups]


def test_two_articles_about_one_announcement_become_one_event() -> None:
    groups = group_signals([IRISH_EXAMINER, GUARDIAN], CONFIG)

    assert len(groups) == 1
    assert keys(groups) == [{"Irish Examiner", "The Guardian"}]


def test_an_announcement_for_another_market_stays_its_own_event() -> None:
    groups = group_signals([IRISH_EXAMINER, GUARDIAN, MOROCCO], CONFIG)

    assert len(groups) == 2
    assert {"Morocco World News"} in keys(groups)
    assert {"Irish Examiner", "The Guardian"} in keys(groups)


def test_the_morocco_signal_is_kept_apart_by_its_publication_gap() -> None:
    grouped, reason = same_event(MOROCCO, GUARDIAN, CONFIG)

    assert grouped is False
    assert reason == PUBLISHED_TOO_FAR_APART


def test_a_populated_market_never_merges_with_a_different_populated_market() -> None:
    romanian = signal("Adevarul", "2026-08-24T09:00:00", market="RO")
    moroccan = signal("Morocco World News", "2026-08-24T10:00:00", market="MA")

    grouped, reason = same_event(romanian, moroccan, CONFIG)

    assert grouped is False
    assert reason == DIFFERENT_MARKET
    assert len(group_signals([romanian, moroccan], CONFIG)) == 2


def test_different_vendors_never_share_an_event() -> None:
    netflix = signal("The Guardian", "2026-08-24T13:45:00")
    digi = signal("The Guardian", "2026-08-24T13:45:00", vendor="DIGI COMMUNICATIONS")

    grouped, reason = same_event(netflix, digi, CONFIG)

    assert grouped is False
    assert reason == DIFFERENT_VENDOR
    assert len(group_signals([netflix, digi], CONFIG)) == 2


def test_two_increases_announced_close_in_time_stay_apart_on_percent() -> None:
    small = signal("Publisher A", "2026-08-24T09:00:00", percent=5.0)
    large = signal("Publisher B", "2026-08-25T09:00:00", percent=19.0)

    grouped, reason = same_event(small, large, CONFIG)

    assert grouped is False
    assert reason == PERCENT_TOO_FAR_APART
    assert len(group_signals([small, large], CONFIG)) == 2


def test_percent_within_tolerance_still_merges() -> None:
    first = signal("Publisher A", "2026-08-24T09:00:00", percent=10.0)
    second = signal("Publisher B", "2026-08-25T09:00:00", percent=12.0)

    assert same_event(first, second, CONFIG)[0] is True
    assert len(group_signals([first, second], CONFIG)) == 1


def test_two_known_effective_dates_never_merge_however_close_the_coverage() -> None:
    september = signal("Publisher A", "2026-08-24T09:00:00", effective="2026-09-02")
    october = signal("Publisher B", "2026-08-24T10:00:00", effective="2026-10-01")

    grouped, reason = same_event(september, october, CONFIG)

    assert grouped is False
    assert reason == DIFFERENT_EFFECTIVE_DATE


def test_the_same_effective_date_merges_across_a_wide_publication_gap() -> None:
    early = signal("Publisher A", "2026-05-01T09:00:00", effective="2026-09-02")
    late = signal("Publisher B", "2026-08-24T10:00:00", effective="2026-09-02")

    assert same_event(early, late, CONFIG)[0] is True
    assert len(group_signals([early, late], CONFIG)) == 1


def test_a_chain_of_near_signals_does_not_swallow_a_distant_one() -> None:
    first = signal("Publisher A", "2026-08-01T09:00:00")
    middle = signal("Publisher B", "2026-08-07T09:00:00")
    last = signal("Publisher C", "2026-08-13T09:00:00")

    groups = group_signals([first, middle, last], CONFIG)

    assert len(groups) == 2
    assert {"Publisher A", "Publisher B"} in keys(groups)
    assert {"Publisher C"} in keys(groups)


def test_grouping_is_independent_of_the_order_signals_arrive_in() -> None:
    rows = [IRISH_EXAMINER, GUARDIAN, MOROCCO]

    forward = keys(group_signals(rows, CONFIG))
    backward = keys(group_signals(list(reversed(rows)), CONFIG))

    assert forward == backward


def test_rerunning_over_unchanged_signals_yields_the_same_event_keys() -> None:
    first_run = [
        build_event(group, CONFIG)
        for group in group_signals([IRISH_EXAMINER, GUARDIAN, MOROCCO], CONFIG)
    ]
    second_run = [
        build_event(group, CONFIG)
        for group in group_signals([MOROCCO, GUARDIAN, IRISH_EXAMINER], CONFIG)
    ]

    assert sorted(event["eventKey"] for event in first_run) == sorted(
        event["eventKey"] for event in second_run
    )


def test_a_later_article_joining_an_event_keeps_the_event_key() -> None:
    before = build_event(group_signals([GUARDIAN], CONFIG)[0], CONFIG)
    latecomer = signal("Le Monde", "2026-08-26T08:00:00")
    after = [
        build_event(group, CONFIG)
        for group in group_signals([GUARDIAN, IRISH_EXAMINER, latecomer], CONFIG)
    ]

    assert [event["eventKey"] for event in after] == [before["eventKey"]]
    assert after[0]["signalCount"] == 3


def test_repeat_coverage_of_one_announcement_does_not_raise_confidence() -> None:
    event = build_event(group_signals([IRISH_EXAMINER, GUARDIAN], CONFIG)[0], CONFIG)

    assert event["signalCount"] == 2
    assert event["publisherCount"] == 2
    assert event["corroborated"] is False
    assert event["confidenceRule"] == REPEAT_COVERAGE_SAME_ANNOUNCEMENT
    assert event["confidence"] == "medium"


def test_two_publishers_reporting_the_same_hard_fact_raise_confidence() -> None:
    first = signal("Publisher A", "2026-08-24T09:00:00", effective="2026-09-02")
    second = signal("Publisher B", "2026-08-25T09:00:00", effective="2026-09-02")

    event = build_event(group_signals([first, second], CONFIG)[0], CONFIG)

    assert event["corroborated"] is True
    assert event["confidenceRule"] == INDEPENDENT_CORROBORATION
    assert event["confidence"] == "high"


def test_a_lone_signal_keeps_its_own_confidence() -> None:
    event = build_event(group_signals([MOROCCO], CONFIG)[0], CONFIG)

    assert event["confidenceRule"] == SINGLE_SIGNAL
    assert event["confidence"] == "high"
    assert event["signalCount"] == 1


def test_the_event_resolves_the_most_specific_value_of_each_field() -> None:
    vague = signal("Publisher A", "2026-08-24T09:00:00", confidence="low")
    precise = signal(
        "Publisher B",
        "2026-08-25T09:00:00",
        effective="2026-09-02",
        market="RO",
        percent=12.0,
        confidence="high",
    )

    event = build_event(group_signals([vague, precise], CONFIG)[0], CONFIG)

    assert event["effectiveDate"] == "2026-09-02"
    assert event["market"] == "RO"
    assert event["percentIncrease"] == 12.0
    assert event["resolvedFrom"]["market"] == "Publisher B"


def test_a_country_market_wins_over_a_global_one() -> None:
    worldwide = signal("Publisher A", "2026-08-24T09:00:00", market="global")
    romanian = signal("Publisher B", "2026-08-25T09:00:00", market="RO")

    assert same_event(worldwide, romanian, CONFIG)[0] is True
    event = build_event(group_signals([worldwide, romanian], CONFIG)[0], CONFIG)

    assert event["market"] == "RO"
    assert event["marketCandidates"] == ["RO", "global"]


def test_the_event_keeps_every_source_article_for_traceability() -> None:
    event = build_event(group_signals([IRISH_EXAMINER, GUARDIAN], CONFIG)[0], CONFIG)

    assert sorted(event["urls"]) == sorted(
        [IRISH_EXAMINER["articleUrl"], GUARDIAN["articleUrl"]]
    )
    assert len(event["articles"]) == 2


def test_rejections_explain_why_two_events_of_one_vendor_stayed_apart() -> None:
    groups = group_signals([IRISH_EXAMINER, GUARDIAN, MOROCCO], CONFIG)

    rows = rejection_reasons(groups, CONFIG)

    assert len(rows) == 1
    assert rows[0]["vendorNormalized"] == "NETFLIX"
    assert PUBLISHED_TOO_FAR_APART in rows[0]["reasons"]
