from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field
from pymongo import AsyncMongoClient, UpdateOne

from backend.vendors.extractor import load_mongo_settings
from backend.vendors.news_watcher import SIGNALS_COLLECTION

EVENTS_COLLECTION = "newsEvents"
EVENT_UNIQUE_KEY = ("source", "eventKey")

LOW = "low"
MEDIUM = "medium"
HIGH = "high"
CONFIDENCE_ORDER = (LOW, MEDIUM, HIGH)

GLOBAL_MARKET = "global"

DIFFERENT_VENDOR = "different_vendor"
DIFFERENT_MARKET = "different_market"
DIFFERENT_EFFECTIVE_DATE = "different_effective_date"
PERCENT_TOO_FAR_APART = "percent_too_far_apart"
PUBLISHED_TOO_FAR_APART = "published_too_far_apart"
NO_USABLE_DATE = "no_usable_date"
SAME_EVENT = "same_event"

SINGLE_SIGNAL = "single_signal"
SAME_PUBLISHER_REPEAT = "same_publisher_repeat"
REPEAT_COVERAGE_SAME_ANNOUNCEMENT = "repeat_coverage_same_announcement"
INDEPENDENT_CORROBORATION = "independent_corroboration"

Signal = dict[str, Any]


class EventsConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_collection: str = SIGNALS_COLLECTION
    target_collection: str = EVENTS_COLLECTION
    vendors: tuple[str, ...] = ()
    proximity_window_days: int = 7
    percent_tolerance_points: float = 3.0
    prune_stale: bool = True
    dry_run: bool = False
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def confidence_rank(value: Any) -> int:
    return CONFIDENCE_ORDER.index(value) if value in CONFIDENCE_ORDER else 0


def raise_confidence(value: str) -> str:
    return CONFIDENCE_ORDER[min(confidence_rank(value) + 1, len(CONFIDENCE_ORDER) - 1)]


def normalised_market(signal: Signal) -> str | None:
    raw = signal.get("market")
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip()
    return GLOBAL_MARKET if value.lower() == GLOBAL_MARKET else value.upper()


def effective_date_of(signal: Signal) -> str | None:
    raw = signal.get("effectiveDate")
    return raw.strip() if isinstance(raw, str) and raw.strip() else None


def percent_of(signal: Signal) -> float | None:
    raw = signal.get("percentIncrease")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw)


def publisher_of(signal: Signal) -> str | None:
    raw = signal.get("publisher")
    return raw.strip() if isinstance(raw, str) and raw.strip() else None


def anchor_at(signal: Signal) -> datetime | None:
    for field in ("publishedAt", "foundAt"):
        value = signal.get(field)
        if isinstance(value, datetime):
            return value
    return None


def far_future() -> datetime:
    return datetime.max.replace(tzinfo=UTC)


def markets_conflict(left: Signal, right: Signal) -> bool:
    first, second = normalised_market(left), normalised_market(right)
    if first is None or second is None:
        return False
    if GLOBAL_MARKET in (first, second):
        return False
    return first != second


def percents_conflict(left: Signal, right: Signal, tolerance: float) -> bool:
    first, second = percent_of(left), percent_of(right)
    if first is None or second is None:
        return False
    return abs(first - second) > tolerance


def dates_agree(left: Signal, right: Signal, window_days: int) -> tuple[bool, str]:
    first, second = effective_date_of(left), effective_date_of(right)
    if first is not None and second is not None:
        if first == second:
            return True, SAME_EVENT
        return False, DIFFERENT_EFFECTIVE_DATE
    left_anchor, right_anchor = anchor_at(left), anchor_at(right)
    if left_anchor is None or right_anchor is None:
        return False, NO_USABLE_DATE
    if abs(left_anchor - right_anchor) <= timedelta(days=window_days):
        return True, SAME_EVENT
    return False, PUBLISHED_TOO_FAR_APART


def same_event(left: Signal, right: Signal, config: EventsConfig) -> tuple[bool, str]:
    if left["vendorNormalized"] != right["vendorNormalized"]:
        return False, DIFFERENT_VENDOR
    if markets_conflict(left, right):
        return False, DIFFERENT_MARKET
    if percents_conflict(left, right, config.percent_tolerance_points):
        return False, PERCENT_TOO_FAR_APART
    return dates_agree(left, right, config.proximity_window_days)


def ordering_key(signal: Signal) -> tuple[str, datetime, str]:
    return (
        signal["vendorNormalized"],
        anchor_at(signal) or far_future(),
        str(signal.get("articleUrl") or ""),
    )


def group_signals(signals: list[Signal], config: EventsConfig) -> list[list[Signal]]:
    groups: list[list[Signal]] = []
    for signal in sorted(signals, key=ordering_key):
        for group in groups:
            if group[0]["vendorNormalized"] != signal["vendorNormalized"]:
                continue
            if all(same_event(member, signal, config)[0] for member in group):
                group.append(signal)
                break
        else:
            groups.append([signal])
    return groups


def event_key(group: list[Signal], config: EventsConfig) -> str:
    seed = group[0]
    material = "|".join(
        (
            config.source_collection,
            seed["vendorNormalized"],
            str(seed.get("articleUrl") or ""),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def resolve_field(
    group: list[Signal],
    value_of: Callable[[Signal], Any],
    penalty: Callable[[Any], int] | None = None,
) -> tuple[Any, Signal | None]:
    carriers = [
        (value_of(signal), signal)
        for signal in group
        if value_of(signal) is not None
    ]
    if not carriers:
        return None, None
    carriers.sort(
        key=lambda row: (
            penalty(row[0]) if penalty else 0,
            -confidence_rank(row[1].get("confidence")),
            anchor_at(row[1]) or far_future(),
            str(row[1].get("articleUrl") or ""),
        )
    )
    return carriers[0][0], carriers[0][1]


def carries_a_hard_fact(signal: Signal) -> bool:
    return effective_date_of(signal) is not None or percent_of(signal) is not None


def combine_confidence(group: list[Signal]) -> tuple[str, str, bool, list[str]]:
    best = CONFIDENCE_ORDER[max(confidence_rank(row.get("confidence")) for row in group)]
    publishers = sorted(
        {name for name in (publisher_of(row) for row in group) if name is not None}
    )
    fact_publishers = {
        name
        for name in (
            publisher_of(row) for row in group if carries_a_hard_fact(row)
        )
        if name is not None
    }

    if len(group) == 1:
        return best, SINGLE_SIGNAL, False, publishers
    if len(fact_publishers) >= 2:
        return raise_confidence(best), INDEPENDENT_CORROBORATION, True, publishers
    if len(publishers) <= 1:
        return best, SAME_PUBLISHER_REPEAT, False, publishers
    return best, REPEAT_COVERAGE_SAME_ANNOUNCEMENT, False, publishers


def article_rows(group: list[Signal]) -> list[dict[str, Any]]:
    return [
        {
            "articleUrl": str(signal.get("articleUrl") or ""),
            "publisher": publisher_of(signal),
            "publishedAt": signal.get("publishedAt"),
            "confidence": signal.get("confidence"),
            "summary": str(signal.get("summary") or ""),
            "sourceApi": signal.get("sourceApi"),
            "language": signal.get("language"),
        }
        for signal in group
    ]


def build_event(group: list[Signal], config: EventsConfig) -> dict[str, Any]:
    seed = group[0]
    percent, percent_from = resolve_field(group, percent_of)
    effective, effective_from = resolve_field(group, effective_date_of)
    market, market_from = resolve_field(
        group,
        normalised_market,
        penalty=lambda value: 1 if value == GLOBAL_MARKET else 0,
    )
    confidence, rule, corroborated, publishers = combine_confidence(group)
    anchors = [value for value in (anchor_at(row) for row in group) if value is not None]

    return {
        "source": config.source_collection,
        "eventKey": event_key(group, config),
        "vendorNormalized": seed["vendorNormalized"],
        "vendorDisplayName": seed.get("vendorDisplayName") or seed["vendorNormalized"],
        "percentIncrease": percent,
        "effectiveDate": effective,
        "market": market,
        "confidence": confidence,
        "confidenceRule": rule,
        "corroborated": corroborated,
        "signalCount": len(group),
        "publisherCount": len(publishers),
        "publishers": publishers,
        "sourceApis": sorted(
            {str(row["sourceApi"]) for row in group if row.get("sourceApi")}
        ),
        "urls": [str(row.get("articleUrl") or "") for row in group],
        "articles": article_rows(group),
        "seedArticleUrl": str(seed.get("articleUrl") or ""),
        "firstPublishedAt": min(anchors) if anchors else None,
        "lastPublishedAt": max(anchors) if anchors else None,
        "percentIncreaseCandidates": sorted(
            {value for value in (percent_of(row) for row in group) if value is not None}
        ),
        "effectiveDateCandidates": sorted(
            {
                value
                for value in (effective_date_of(row) for row in group)
                if value is not None
            }
        ),
        "marketCandidates": sorted(
            {
                value
                for value in (normalised_market(row) for row in group)
                if value is not None
            }
        ),
        "resolvedFrom": {
            "percentIncrease": publisher_of(percent_from) if percent_from else None,
            "effectiveDate": publisher_of(effective_from) if effective_from else None,
            "market": publisher_of(market_from) if market_from else None,
        },
        "windowDaysApplied": config.proximity_window_days,
        "percentToleranceApplied": config.percent_tolerance_points,
        "updatedAt": config.generated_at,
    }


def rejection_reasons(
    groups: list[list[Signal]], config: EventsConfig
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, group in enumerate(groups):
        for other in groups[index + 1 :]:
            if group[0]["vendorNormalized"] != other[0]["vendorNormalized"]:
                continue
            reasons = sorted(
                {
                    same_event(member, candidate, config)[1]
                    for member in group
                    for candidate in other
                }
                - {SAME_EVENT}
            )
            rows.append(
                {
                    "vendorNormalized": group[0]["vendorNormalized"],
                    "leftKey": event_key(group, config),
                    "rightKey": event_key(other, config),
                    "leftPublisher": publisher_of(group[0]),
                    "rightPublisher": publisher_of(other[0]),
                    "reasons": reasons,
                }
            )
    return rows


async def ensure_target(db: Any, config: EventsConfig) -> None:
    await db[config.target_collection].create_index(
        [(field, 1) for field in EVENT_UNIQUE_KEY],
        unique=True,
        name="news_event_unique",
    )
    await db[config.target_collection].create_index(
        [("source", 1), ("vendorNormalized", 1), ("lastPublishedAt", -1)]
    )
    await db[config.target_collection].create_index([("source", 1), ("effectiveDate", 1)])


async def load_signals(db: Any, config: EventsConfig) -> list[Signal]:
    query: dict[str, Any] = {}
    if config.vendors:
        query["vendorNormalized"] = {"$in": [value.upper() for value in config.vendors]}
    return await db[config.source_collection].find(query).to_list(length=None)


async def run(db: Any, config: EventsConfig) -> dict[str, Any]:
    signals = await load_signals(db, config)
    groups = group_signals(signals, config)
    events = [build_event(group, config) for group in groups]

    pruned = 0
    if not config.dry_run:
        await ensure_target(db, config)
        if events:
            await db[config.target_collection].bulk_write(
                [
                    UpdateOne(
                        {field: event[field] for field in EVENT_UNIQUE_KEY},
                        {
                            "$set": event,
                            "$setOnInsert": {"createdAt": config.generated_at},
                        },
                        upsert=True,
                    )
                    for event in events
                ],
                ordered=False,
            )
        if config.prune_stale:
            outcome = await db[config.target_collection].delete_many(
                {
                    "source": config.source_collection,
                    "eventKey": {"$nin": [event["eventKey"] for event in events]},
                }
            )
            pruned = outcome.deleted_count

    return {
        "signals": signals,
        "groups": groups,
        "events": events,
        "rejections": rejection_reasons(groups, config),
        "pruned": pruned,
    }


def report(outcome: dict[str, Any], config: EventsConfig) -> None:
    events: list[dict[str, Any]] = outcome["events"]
    print(f"\nsignals collection : {config.source_collection}")
    print(f"events collection  : {config.target_collection}")
    print(
        f"grouping rules     : window={config.proximity_window_days}d  "
        f"percent tolerance={config.percent_tolerance_points}pp"
    )
    print(f"\n{len(outcome['signals'])} raw signals -> {len(events)} events")
    if outcome["pruned"]:
        print(f"pruned stale events: {outcome['pruned']}")

    for event in sorted(
        events, key=lambda row: (row["vendorNormalized"], str(row["firstPublishedAt"]))
    ):
        percent = (
            f"{event['percentIncrease']}%"
            if event["percentIncrease"] is not None
            else "unspecified"
        )
        print()
        print(
            f"  {event['vendorNormalized']:<22} {percent:<12} "
            f"effective {event['effectiveDate'] or 'unknown':<12} "
            f"market {event['market'] or 'unknown':<8} "
            f"confidence {event['confidence']} ({event['confidenceRule']})"
        )
        print(
            f"     key {event['eventKey'][:16]}  signals {event['signalCount']}  "
            f"publishers {event['publisherCount']}  "
            f"corroborated {str(event['corroborated']).lower()}"
        )
        for article in event["articles"]:
            print(
                f"     - {str(article['publisher'] or 'unknown')[:22]:<24} "
                f"{article['summary'][:88]}"
            )

    if outcome["rejections"]:
        print("\nkept apart (same vendor, different event):")
        for row in outcome["rejections"]:
            print(
                f"  {row['vendorNormalized']:<22} "
                f"{str(row['leftPublisher'] or 'unknown')[:22]:<24} vs "
                f"{str(row['rightPublisher'] or 'unknown')[:22]:<24} "
                f"{','.join(row['reasons'])}"
            )


async def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=SIGNALS_COLLECTION)
    parser.add_argument("--target", default=EVENTS_COLLECTION)
    parser.add_argument("--vendor", action="append", default=None)
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--percent-tolerance", type=float, default=3.0)
    parser.add_argument("--keep-stale", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()

    config = EventsConfig(
        source_collection=arguments.source,
        target_collection=arguments.target,
        vendors=tuple(arguments.vendor or ()),
        proximity_window_days=arguments.window_days,
        percent_tolerance_points=arguments.percent_tolerance,
        prune_stale=not arguments.keep_stale,
        dry_run=arguments.dry_run,
    )

    uri, db_name = load_mongo_settings()
    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(
        uri, uuidRepresentation="standard", tz_aware=True, serverSelectionTimeoutMS=10000
    )
    try:
        outcome = await run(client[db_name], config)
        report(outcome, config)
    finally:
        await client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
