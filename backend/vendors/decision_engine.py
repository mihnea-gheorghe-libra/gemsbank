from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pymongo import AsyncMongoClient, UpdateOne

from backend.vendors.detector import (
    ALERTS_COLLECTION,
    CONFIRMED,
    PREDICTIVE,
    YEAR_OVER_YEAR,
    DetectorConfig,
    percent_change,
    resolve_baseline,
)
from backend.vendors.extractor import STATS_COLLECTION, load_mongo_settings
from backend.vendors.user_prices import USER_PRICES_COLLECTION, load_user_series

EVENTS_COLLECTION = "newsEvents"
NOTIFICATIONS_COLLECTION = "userNotifications"
NOTIFICATION_UNIQUE_KEY = (
    "source",
    "userId",
    "vendorNormalized",
    "currency",
    "month",
    "alertType",
)

HIGH = "high"
MEDIUM = "medium"
LOW = "low"

PENDING = "pending"

SAME_PRICE_STATE = "same_price_state_already_notified"
SAME_NEWS_EPISODE = "same_news_episode_already_notified"

DUAL_CORROBORATED = "dual_corroborated"
INTERNAL_MATHEMATICAL = "internal_mathematical"
COLD_START_UNBLOCKED_BY_NEWS = "cold_start_unblocked_by_news"
EXTERNAL_NEWS_PREDICTIVE = "external_news_predictive"

SUBJECT_BY_CATEGORY = {
    "entertainment": "Abonamentul tău la {vendor}",
    "utilities": "Factura ta la {vendor}",
    "transport": "Cât plătești la {vendor}",
    "groceries": "Cât plătești la {vendor}",
}
DEFAULT_SUBJECT = "Plățile tale la {vendor}"

SUBJECT_BY_CATEGORY_EN = {
    "entertainment": "Your {vendor} subscription",
    "utilities": "Your {vendor} bill",
    "transport": "What you pay at {vendor}",
    "groceries": "What you pay at {vendor}",
}
DEFAULT_SUBJECT_EN = "Your payments to {vendor}"

VERB_BY_CONFIDENCE = {
    HIGH: "s-a scumpit cu",
    MEDIUM: "s-a scumpit cu",
    LOW: "ar putea să se fi scumpit cu",
}

VERB_BY_CONFIDENCE_EN = {
    HIGH: "increased by",
    MEDIUM: "increased by",
    LOW: "might have increased by",
}

SHORT_TEXT_LIMIT = 60


class DecisionConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_collection: str = "payments_seed_seasonal"
    alerts_collection: str = ALERTS_COLLECTION
    stats_collection: str = STATS_COLLECTION
    user_prices_collection: str = USER_PRICES_COLLECTION
    events_collection: str = EVENTS_COLLECTION
    notifications_collection: str = NOTIFICATIONS_COLLECTION
    include_low_confidence: bool = False
    include_predictive_news: bool = True
    repeat_price_tolerance: float = 0.03
    repeat_step_tolerance: float = 0.12
    news_episode_window_days: int = 180
    min_user_increase: float = 0.08
    baseline_months: int = 3
    year_window_months: int = 1
    use_year_over_year: bool = True
    rebuild: bool = True
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def baseline_config(config: DecisionConfig) -> DetectorConfig:
    return DetectorConfig(
        source_collection=config.source_collection,
        baseline_months=config.baseline_months,
        year_window_months=config.year_window_months,
        use_year_over_year=config.use_year_over_year,
    )


def confidence_for(alert: dict[str, Any]) -> str:
    return HIGH if alert.get("baselineMethod") == YEAR_OVER_YEAR else LOW


BASELINE_SLOT = "{baseline}"
OBSERVED_SLOT = "{observed}"


def news_matches_vendor(
    event: dict[str, Any],
    vendor: str,
    currency: str = "RON",
) -> bool:
    if event.get("vendorNormalized") != vendor:
        return False
    market = event.get("market")
    if currency == "RON" and market:
        if market.upper() not in ("RO", "GLOBAL"):
            return False
    return True


def news_matches_alert(
    event: dict[str, Any],
    alert: dict[str, Any],
) -> bool:
    if not news_matches_vendor(event, alert["vendor"], alert.get("currency", "RON")):
        return False
    effective = event.get("effectiveDate")
    alert_month = alert.get("month")
    if effective and alert_month:
        effective_month = effective[:7]
        alert_y, alert_m = int(alert_month[:4]), int(alert_month[5:7])
        eff_y, eff_m = int(effective_month[:4]), int(effective_month[5:7])
        diff_months = abs((alert_y * 12 + alert_m) - (eff_y * 12 + eff_m))
        if diff_months > 4:
            return False
    return True


def evaluate_internal_alert(
    alert: dict[str, Any],
    matching_events: list[dict[str, Any]],
) -> tuple[str, str, dict[str, Any] | None]:
    base_confidence = HIGH if alert.get("baselineMethod") == YEAR_OVER_YEAR else LOW
    best_event = matching_events[0] if matching_events else None

    if base_confidence == HIGH:
        if best_event:
            return HIGH, DUAL_CORROBORATED, best_event
        return HIGH, INTERNAL_MATHEMATICAL, None

    if best_event:
        news_conf = best_event.get("confidence", MEDIUM)
        resolved_conf = HIGH if news_conf == HIGH else MEDIUM
        return resolved_conf, COLD_START_UNBLOCKED_BY_NEWS, best_event

    return LOW, "unconfirmed_cold_start", None


def render_short(
    display_name: str, percent: float, news_event: dict[str, Any] | None = None
) -> str:
    text = f"{display_name} +{round(percent * 100)}%"
    if len(text) <= SHORT_TEXT_LIMIT:
        return text
    room = SHORT_TEXT_LIMIT - len(f" +{round(percent * 100)}%") - 1
    return f"{display_name[:room]}… +{round(percent * 100)}%"


def render_long(
    display_name: str,
    category: str,
    confidence: str,
    percent: float,
    baseline_minor: int,
    observed_minor: int,
    currency: str,
    news_event: dict[str, Any] | None = None,
) -> str:
    subject = SUBJECT_BY_CATEGORY.get(category, DEFAULT_SUBJECT).format(
        vendor=display_name
    )
    verb = VERB_BY_CONFIDENCE.get(confidence, "s-a scumpit cu")
    base_text = (
        f"{subject} {verb} {round(percent * 100)}% "
        f"(de la {BASELINE_SLOT} la {OBSERVED_SLOT})"
    )
    if news_event and news_event.get("publishers"):
        pubs = ", ".join(news_event["publishers"])
        base_text += f" — confirmat în presă ({pubs})"
    return base_text


def render_news_predictive_short(display_name: str, percent: float | None) -> str:
    if percent is not None:
        text = f"{display_name} +{round(percent)}% (anunțat)"
    else:
        text = f"{display_name}: scumpire anunțată"
    if len(text) <= SHORT_TEXT_LIMIT:
        return text
    return text[: SHORT_TEXT_LIMIT - 1] + "…"


def render_news_predictive_long(
    display_name: str,
    category: str,
    event: dict[str, Any],
    last_price_minor: int,
    currency: str,
) -> str:
    subject = SUBJECT_BY_CATEGORY.get(category, DEFAULT_SUBJECT).format(
        vendor=display_name
    )
    pubs = ", ".join(event.get("publishers") or ["Presă"])
    effective = event.get("effectiveDate")
    percent = event.get("percentIncrease")

    details = []
    if percent is not None:
        details.append(f"cu ~{round(percent)}%")
    if effective:
        details.append(f"din {effective}")

    detail_str = f" ({', '.join(details)})" if details else ""
    return (
        f"{subject}: {display_name} a anunțat o majorare de preț{detail_str}, "
        f"conform relatărilor din presă ({pubs}). "
        f"Ultima ta plată a fost de {BASELINE_SLOT}."
    )


def render_short_en(
    display_name: str, percent: float, news_event: dict[str, Any] | None = None
) -> str:
    text = f"{display_name} +{round(percent * 100)}%"
    if len(text) <= SHORT_TEXT_LIMIT:
        return text
    room = SHORT_TEXT_LIMIT - len(f" +{round(percent * 100)}%") - 1
    return f"{display_name[:room]}… +{round(percent * 100)}%"


def render_long_en(
    display_name: str,
    category: str,
    confidence: str,
    percent: float,
    baseline_minor: int,
    observed_minor: int,
    currency: str,
    news_event: dict[str, Any] | None = None,
) -> str:
    subject = SUBJECT_BY_CATEGORY_EN.get(category, DEFAULT_SUBJECT_EN).format(
        vendor=display_name
    )
    verb = VERB_BY_CONFIDENCE_EN.get(confidence, "increased by")
    base_text = (
        f"{subject} {verb} {round(percent * 100)}% "
        f"(from {BASELINE_SLOT} to {OBSERVED_SLOT})"
    )
    if news_event and news_event.get("publishers"):
        pubs = ", ".join(news_event["publishers"])
        base_text += f" — confirmed in press ({pubs})"
    return base_text


def render_news_predictive_short_en(
    display_name: str, percent: float | None
) -> str:
    if percent is not None:
        text = f"{display_name} +{round(percent)}% (announced)"
    else:
        text = f"{display_name}: price increase announced"
    if len(text) <= SHORT_TEXT_LIMIT:
        return text
    return text[: SHORT_TEXT_LIMIT - 1] + "…"


def render_news_predictive_long_en(
    display_name: str,
    category: str,
    event: dict[str, Any],
    last_price_minor: int,
    currency: str,
) -> str:
    subject = SUBJECT_BY_CATEGORY_EN.get(category, DEFAULT_SUBJECT_EN).format(
        vendor=display_name
    )
    pubs = ", ".join(event.get("publishers") or ["Press"])
    effective = event.get("effectiveDate")
    percent = event.get("percentIncrease")

    details = []
    if percent is not None:
        details.append(f"by ~{round(percent)}%")
    if effective:
        details.append(f"from {effective}")

    detail_str = f" ({', '.join(details)})" if details else ""
    return (
        f"{subject}: {display_name} announced a price increase{detail_str}, "
        f"according to press reports ({pubs}). "
        f"Your last payment was {BASELINE_SLOT}."
    )


def vendor_profiles(
    stats_rows: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, str]]:
    variants: dict[tuple[str, str], Counter[str]] = {}
    categories: dict[tuple[str, str], Counter[str]] = {}
    for row in stats_rows:
        key = (row["vendorNormalized"], row["currency"])
        variants.setdefault(key, Counter()).update(row.get("counterpartyVariants", []))
        categories.setdefault(key, Counter()).update(row.get("categories", []))

    profiles: dict[tuple[str, str], dict[str, str]] = {}
    for key in variants:
        name_counts = variants[key]
        best_name = min(
            name_counts, key=lambda name: (-name_counts[name], name), default=key[0]
        )
        category_counts = categories.get(key, Counter())
        best_category = min(
            category_counts,
            key=lambda value: (-category_counts[value], value),
            default="",
        )
        profiles[key] = {"displayName": best_name, "category": best_category}
    return profiles


def affected_users(
    user_series: dict[tuple[str, str, str], list[dict[str, Any]]],
    alert: dict[str, Any],
    config: DecisionConfig,
) -> list[dict[str, Any]]:
    vendor = alert["vendor"]
    currency = alert["currency"]
    month_label = alert["month"]
    detector = baseline_config(config)

    people: list[dict[str, Any]] = []
    for (series_vendor, series_currency, user_id), months in user_series.items():
        if series_vendor != vendor or series_currency != currency:
            continue
        prices = {month["month"]: month["priceMinorUnits"] for month in months}
        if month_label not in prices:
            continue
        resolved = resolve_baseline(prices, month_label, detector)
        if resolved is None:
            continue
        baseline, method, window = resolved
        observed = prices[month_label]
        increase = percent_change(observed, baseline)
        if increase < config.min_user_increase:
            continue
        people.append(
            {
                "userId": user_id,
                "baselineMinorUnits": baseline,
                "observedMinorUnits": observed,
                "percentChange": increase,
                "userBaselineMethod": method,
                "userBaselineMonths": window,
            }
        )
    people.sort(key=lambda row: row["userId"])
    return people


def active_subscribers(
    user_series: dict[tuple[str, str, str], list[dict[str, Any]]],
    vendor: str,
    currency: str,
) -> list[dict[str, Any]]:
    subscribers: list[dict[str, Any]] = []
    for (series_vendor, series_currency, user_id), months in user_series.items():
        if series_vendor != vendor or series_currency != currency:
            continue
        if not months:
            continue
        recent = sorted(months, key=lambda m: m["month"])[-1]
        subscribers.append(
            {
                "userId": user_id,
                "lastPriceMinorUnits": recent["priceMinorUnits"],
                "lastMonth": recent["month"],
            }
        )
    subscribers.sort(key=lambda s: s["userId"])
    return subscribers


def relative_gap(current: int, previous: int) -> float:
    if previous == 0:
        return 1.0 if current else 0.0
    return abs(current - previous) / abs(previous)


def repeats_notified_change(
    previous: dict[str, Any],
    observed_minor: int,
    step: float,
    config: DecisionConfig,
) -> bool:
    price_held = (
        relative_gap(observed_minor, previous["observedMinorUnits"])
        <= config.repeat_price_tolerance
    )
    step_held = abs(step - previous["percentChange"]) <= config.repeat_step_tolerance
    return price_held or step_held


def as_grouping_signal(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "vendorNormalized": event["vendorNormalized"],
        "effectiveDate": event.get("effectiveDate"),
        "publishedAt": event.get("firstPublishedAt"),
        "foundAt": event.get("lastPublishedAt"),
        "percentIncrease": event.get("percentIncrease"),
        "market": event.get("market"),
        "confidence": event.get("confidence"),
        "articleUrl": event.get("eventKey") or "",
    }


def news_episodes(
    events: list[dict[str, Any]], config: DecisionConfig
) -> tuple[dict[str, str], dict[str, list[str]], dict[str, list[str]]]:
    from backend.vendors.news_events import EventsConfig, group_signals

    usable = [event for event in events if event.get("vendorNormalized")]
    grouping = EventsConfig(proximity_window_days=config.news_episode_window_days)
    by_key = {event.get("eventKey") or "": event for event in usable}

    dated = [row for row in usable if row.get("effectiveDate")]
    undated = [row for row in usable if not row.get("effectiveDate")]
    groups = group_signals(
        [as_grouping_signal(row) for row in dated], grouping
    ) + group_signals([as_grouping_signal(row) for row in undated], grouping)

    episode_of: dict[str, str] = {}
    publishers: dict[str, list[str]] = {}
    urls: dict[str, list[str]] = {}
    for group in groups:
        episode = group[0]["articleUrl"]
        seen_publishers: list[str] = []
        seen_urls: list[str] = []
        for row in group:
            key = row["articleUrl"]
            episode_of[key] = episode
            event = by_key.get(key, {})
            for name in event.get("publishers") or []:
                if name not in seen_publishers:
                    seen_publishers.append(name)
            for url in event.get("urls") or []:
                if url not in seen_urls:
                    seen_urls.append(url)
        publishers[episode] = seen_publishers
        urls[episode] = seen_urls
    return episode_of, publishers, urls


def build_notifications(
    alerts: list[dict[str, Any]],
    profiles: dict[tuple[str, str], dict[str, str]],
    user_series: dict[tuple[str, str, str], list[dict[str, Any]]],
    config: DecisionConfig,
    news_events: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events = list(news_events or [])
    notifications: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    registered_keys: set[tuple[str, str, str, str, str, str]] = set()
    covered_episodes: set[str] = set()
    covered_user_months: set[tuple[str, str, str, str]] = set()
    notified_state: dict[tuple[str, str, str], dict[str, Any]] = {}
    notified_episodes: set[tuple[str, str, str, str]] = set()
    episode_of, episode_publishers, episode_urls = news_episodes(events, config)

    for alert in sorted(
        alerts,
        key=lambda row: (
            row["vendor"],
            row["month"],
            0 if row["alertType"] == CONFIRMED else 1,
        ),
    ):
        matching = [event for event in events if news_matches_alert(event, alert)]
        confidence, origin, best_event = evaluate_internal_alert(alert, matching)

        if confidence == LOW and not config.include_low_confidence:
            skipped.append(
                {
                    "vendor": alert["vendor"],
                    "month": alert["month"],
                    "alertType": alert["alertType"],
                    "confidence": confidence,
                    "reason": "low_confidence_suppressed",
                    "origin": origin,
                    "baselineMethod": alert.get("baselineMethod"),
                    "percentChange": alert["percentChange"],
                }
            )
            continue

        profile = profiles.get(
            (alert["vendor"], alert["currency"]),
            {"displayName": alert["vendor"], "category": ""},
        )
        people = affected_users(user_series, alert, config)
        if not people:
            skipped.append(
                {
                    "vendor": alert["vendor"],
                    "month": alert["month"],
                    "alertType": alert["alertType"],
                    "confidence": confidence,
                    "reason": "no_user_moved",
                    "origin": origin,
                    "baselineMethod": alert.get("baselineMethod"),
                    "percentChange": alert["percentChange"],
                }
            )
            continue

        episode = episode_of.get(best_event.get("eventKey") or "") if best_event else None
        if episode:
            covered_episodes.add(episode)
        sourced_event = (
            {**best_event, "publishers": episode_publishers.get(episode, [])}
            if best_event and episode
            else best_event
        )

        for person in people:
            state_key = (person["userId"], alert["vendor"], alert["currency"])
            previous = notified_state.get(state_key)
            if previous is not None and repeats_notified_change(
                previous, person["observedMinorUnits"], person["percentChange"], config
            ):
                skipped.append(
                    {
                        "vendor": alert["vendor"],
                        "month": alert["month"],
                        "alertType": alert["alertType"],
                        "confidence": confidence,
                        "reason": SAME_PRICE_STATE,
                        "origin": origin,
                        "userId": person["userId"],
                        "baselineMethod": alert.get("baselineMethod"),
                        "percentChange": person["percentChange"],
                        "notifiedMonth": previous["month"],
                        "notifiedObservedMinorUnits": previous["observedMinorUnits"],
                        "observedMinorUnits": person["observedMinorUnits"],
                    }
                )
                continue
            notified_state[state_key] = {
                "month": alert["month"],
                "observedMinorUnits": person["observedMinorUnits"],
                "percentChange": person["percentChange"],
            }
            if episode:
                notified_episodes.add(
                    (person["userId"], alert["vendor"], alert["currency"], episode)
                )
            key = (
                config.source_collection,
                person["userId"],
                alert["vendor"],
                alert["currency"],
                alert["month"],
                alert["alertType"],
            )
            registered_keys.add(key)
            covered_user_months.add(
                (person["userId"], alert["vendor"], alert["currency"], alert["month"])
            )
            notifications.append(
                {
                    "source": config.source_collection,
                    "userId": person["userId"],
                    "vendorNormalized": alert["vendor"],
                    "vendorDisplayName": profile["displayName"],
                    "vendorCategory": profile["category"],
                    "currency": alert["currency"],
                    "month": alert["month"],
                    "alertType": alert["alertType"],
                    "confidence": confidence,
                    "origin": origin,
                    "baselineMethod": alert.get("baselineMethod"),
                    "userBaselineMethod": person["userBaselineMethod"],
                    "percentChange": round(person["percentChange"], 6),
                    "vendorPercentChange": alert["percentChange"],
                    "baselineMinorUnits": person["baselineMinorUnits"],
                    "observedMinorUnits": person["observedMinorUnits"],
                    "shortText": render_short(
                        profile["displayName"],
                        person["percentChange"],
                        news_event=sourced_event,
                    ),
                    "longText": render_long(
                        profile["displayName"],
                        profile["category"],
                        confidence,
                        person["percentChange"],
                        person["baselineMinorUnits"],
                        person["observedMinorUnits"],
                        alert["currency"],
                        news_event=sourced_event,
                    ),
                    "shortTextEn": render_short_en(
                        profile["displayName"],
                        person["percentChange"],
                        news_event=sourced_event,
                    ),
                    "longTextEn": render_long_en(
                        profile["displayName"],
                        profile["category"],
                        confidence,
                        person["percentChange"],
                        person["baselineMinorUnits"],
                        person["observedMinorUnits"],
                        alert["currency"],
                        news_event=sourced_event,
                    ),
                    "newsEventKey": best_event.get("eventKey") if best_event else None,
                    "newsPublishers": episode_publishers.get(episode)
                    if episode
                    else None,
                    "newsUrls": episode_urls.get(episode) if episode else None,
                    "newsEffectiveDate": best_event.get("effectiveDate")
                    if best_event
                    else None,
                    "newsMarket": best_event.get("market") if best_event else None,
                    "status": PENDING,
                    "createdAt": config.generated_at,
                }
            )

    if config.include_predictive_news:
        for event in sorted(
            events,
            key=lambda e: (
                e.get("vendorNormalized", ""),
                str(e.get("effectiveDate") or e.get("firstPublishedAt") or ""),
            ),
        ):
            episode = episode_of.get(event.get("eventKey") or "")
            if episode and episode in covered_episodes:
                skipped.append(
                    {
                        "vendor": event["vendorNormalized"],
                        "month": None,
                        "alertType": PREDICTIVE,
                        "confidence": event.get("confidence"),
                        "reason": SAME_NEWS_EPISODE,
                        "origin": EXTERNAL_NEWS_PREDICTIVE,
                        "eventKey": event.get("eventKey"),
                        "episode": episode,
                        "publishers": event.get("publishers"),
                    }
                )
                continue

            vendor = event["vendorNormalized"]
            currencies = {
                k[1] for k in user_series.keys() if k[0] == vendor
            } or {"RON"}
            for currency in sorted(currencies):
                if not news_matches_vendor(event, vendor, currency):
                    continue

                if event.get("effectiveDate"):
                    target_month = event["effectiveDate"][:7]
                elif event.get("firstPublishedAt") and hasattr(
                    event["firstPublishedAt"], "strftime"
                ):
                    target_month = event["firstPublishedAt"].strftime("%Y-%m")
                else:
                    target_month = config.generated_at.strftime("%Y-%m")

                subscribers = active_subscribers(user_series, vendor, currency)
                if not subscribers:
                    continue

                sourced_event = (
                    {**event, "publishers": episode_publishers.get(episode, [])}
                    if episode
                    else event
                )

                profile = profiles.get(
                    (vendor, currency),
                    {
                        "displayName": event.get("vendorDisplayName") or vendor,
                        "category": "",
                    },
                )

                pct_inc = event.get("percentIncrease")
                pct_change = (
                    round(float(pct_inc) / 100.0, 6) if pct_inc is not None else None
                )

                for subscriber in subscribers:
                    if (
                        subscriber["userId"],
                        vendor,
                        currency,
                        target_month,
                    ) in covered_user_months:
                        continue

                    if episode and (
                        subscriber["userId"],
                        vendor,
                        currency,
                        episode,
                    ) in notified_episodes:
                        continue

                    key = (
                        config.source_collection,
                        subscriber["userId"],
                        vendor,
                        currency,
                        target_month,
                        PREDICTIVE,
                    )
                    if key in registered_keys:
                        continue
                    registered_keys.add(key)
                    covered_user_months.add(
                        (subscriber["userId"], vendor, currency, target_month)
                    )
                    if episode:
                        notified_episodes.add(
                            (subscriber["userId"], vendor, currency, episode)
                        )
                        covered_episodes.add(episode)

                    last_price = subscriber["lastPriceMinorUnits"]
                    observed_expected = (
                        round(last_price * (1.0 + pct_change))
                        if pct_change is not None
                        else last_price
                    )

                    notifications.append(
                        {
                            "source": config.source_collection,
                            "userId": subscriber["userId"],
                            "vendorNormalized": vendor,
                            "vendorDisplayName": profile["displayName"],
                            "vendorCategory": profile["category"],
                            "currency": currency,
                            "month": target_month,
                            "alertType": PREDICTIVE,
                            "confidence": event.get("confidence", HIGH),
                            "origin": EXTERNAL_NEWS_PREDICTIVE,
                            "baselineMethod": "external_press",
                            "userBaselineMethod": "external_press",
                            "percentChange": pct_change,
                            "vendorPercentChange": pct_change,
                            "baselineMinorUnits": last_price,
                            "observedMinorUnits": observed_expected,
                            "shortText": render_news_predictive_short(
                                profile["displayName"], pct_inc
                            ),
                            "longText": render_news_predictive_long(
                                profile["displayName"],
                                profile["category"],
                                sourced_event,
                                last_price,
                                currency,
                            ),
                            "shortTextEn": render_news_predictive_short_en(
                                profile["displayName"], pct_inc
                            ),
                            "longTextEn": render_news_predictive_long_en(
                                profile["displayName"],
                                profile["category"],
                                sourced_event,
                                last_price,
                                currency,
                            ),
                            "newsEventKey": event.get("eventKey"),
                            "newsPublishers": episode_publishers.get(
                                episode, event.get("publishers")
                            ),
                            "newsUrls": episode_urls.get(episode, event.get("urls")),
                            "newsEffectiveDate": event.get("effectiveDate"),
                            "newsMarket": event.get("market"),
                            "status": PENDING,
                            "createdAt": config.generated_at,
                        }
                    )

    return notifications, skipped


async def ensure_target(db: Any, config: DecisionConfig) -> None:
    await db[config.notifications_collection].create_index(
        [(field, 1) for field in NOTIFICATION_UNIQUE_KEY],
        unique=True,
        name="user_notification_unique",
    )
    await db[config.notifications_collection].create_index(
        [("source", 1), ("userId", 1), ("createdAt", -1)]
    )
    await db[config.notifications_collection].create_index(
        [("source", 1), ("status", 1)]
    )
    await db[config.notifications_collection].create_index(
        [("source", 1), ("origin", 1)]
    )


async def run(
    db: Any, config: DecisionConfig
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    await ensure_target(db, config)
    if config.rebuild:
        await db[config.notifications_collection].delete_many(
            {"source": config.source_collection}
        )

    alerts = (
        await db[config.alerts_collection]
        .find({"source": config.source_collection})
        .to_list(length=None)
    )
    stats_rows = (
        await db[config.stats_collection]
        .find({"source": config.source_collection})
        .to_list(length=None)
    )
    user_series = await load_user_series(
        db, config.source_collection, config.user_prices_collection
    )
    news_events = (
        await db[config.events_collection].find({}).to_list(length=None)
        if config.events_collection in await db.list_collection_names()
        else []
    )

    notifications, skipped = build_notifications(
        alerts, vendor_profiles(stats_rows), user_series, config, news_events
    )

    written = {"inserted": 0, "unchanged": 0}
    if notifications:
        result = await db[config.notifications_collection].bulk_write(
            [
                UpdateOne(
                    {field: row[field] for field in NOTIFICATION_UNIQUE_KEY},
                    {"$set": row},
                    upsert=True,
                )
                for row in notifications
            ],
            ordered=False,
        )
        written["inserted"] = result.upserted_count
        written["unchanged"] = len(notifications) - result.upserted_count
    return notifications, skipped, written


def report(
    notifications: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    written: dict[str, int],
    config: DecisionConfig,
) -> None:
    print(f"\nsource        : {config.source_collection}")
    print(f"target        : {config.notifications_collection}")
    print(f"news events   : {config.events_collection}")
    print(
        f"low confidence: {'included, marked' if config.include_low_confidence else 'suppressed'}"
    )
    print(f"user filter   : own price up at least {config.min_user_increase:.0%}")
    print(
        f"notifications : {len(notifications)} "
        f"({written['inserted']} new, {written['unchanged']} already on record)\n"
    )

    counts = Counter(row["confidence"] for row in notifications)
    origins = Counter(row.get("origin", "unknown") for row in notifications)
    users_by_confidence = {
        level: len(
            {row["userId"] for row in notifications if row["confidence"] == level}
        )
        for level in (HIGH, MEDIUM, LOW)
    }
    header = (
        f"{'confidence':<14}{'notifications':>15}{'distinct users':>16}{'vendors':>10}"
    )
    print(header)
    print("-" * len(header))
    for level in (HIGH, MEDIUM, LOW):
        vendors = len(
            {
                row["vendorNormalized"]
                for row in notifications
                if row["confidence"] == level
            }
        )
        print(
            f"{level:<14}{counts.get(level, 0):>15}{users_by_confidence[level]:>16}{vendors:>10}"
        )

    print("\nbreakdown by decision origin:")
    for origin, count in sorted(origins.items()):
        print(f"  {origin:<32}: {count:>5} notifications")

    seen: set[tuple[str, str, str]] = set()
    print("\nexample texts, one per (vendor, month, alertType):")
    for row in notifications:
        key = (row["vendorNormalized"], row["month"], row["alertType"])
        if key in seen:
            continue
        seen.add(key)
        print(
            f"  [{row['confidence']:<6}] [{row.get('origin', 'internal'):<28}] "
            f"{row['vendorNormalized']} {row['month']} {row['alertType']}"
        )
        print(f"     short ({len(row['shortText']):>2} chars): {row['shortText']}")
        print(f"     long : {row['longText']}")

    suppressed = [
        row for row in skipped if row["reason"] == "low_confidence_suppressed"
    ]
    quiet = [row for row in skipped if row["reason"] == "no_user_moved"]
    print(f"\nsuppressed low-confidence alerts : {len(suppressed)}")
    for row in suppressed:
        print(
            f"  {row['vendor']:<22} {row['month']}  {row['alertType']:<10} "
            f"{row['percentChange']:+.2%}  [{row['baselineMethod']}] (origin: {row.get('origin')})"
        )
    print(f"alerts where no user actually moved : {len(quiet)}")
    for row in quiet:
        print(f"  {row['vendor']:<22} {row['month']}  {row['alertType']}")


async def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="payments_seed_seasonal")
    parser.add_argument("--alerts", default=ALERTS_COLLECTION)
    parser.add_argument("--stats", default=STATS_COLLECTION)
    parser.add_argument("--user-prices", default=USER_PRICES_COLLECTION)
    parser.add_argument("--events", default=EVENTS_COLLECTION)
    parser.add_argument("--target", default=NOTIFICATIONS_COLLECTION)
    parser.add_argument("--include-low-confidence", action="store_true")
    parser.add_argument("--min-user-increase", type=float, default=0.08)
    parser.add_argument("--no-predictive-news", action="store_true")
    parser.add_argument("--no-rebuild", action="store_true")
    arguments = parser.parse_args()

    config = DecisionConfig(
        source_collection=arguments.source,
        alerts_collection=arguments.alerts,
        stats_collection=arguments.stats,
        user_prices_collection=arguments.user_prices,
        events_collection=arguments.events,
        notifications_collection=arguments.target,
        include_low_confidence=arguments.include_low_confidence,
        include_predictive_news=not arguments.no_predictive_news,
        min_user_increase=arguments.min_user_increase,
        rebuild=not arguments.no_rebuild,
    )

    uri, db_name = load_mongo_settings()
    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(
        uri,
        uuidRepresentation="standard",
        tz_aware=True,
        serverSelectionTimeoutMS=10000,
    )
    try:
        notifications, skipped, written = await run(client[db_name], config)
        report(notifications, skipped, written, config)
    finally:
        await client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
