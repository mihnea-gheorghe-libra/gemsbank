from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pymongo import AsyncMongoClient, UpdateOne

from backend.vendors.extractor import STATS_COLLECTION, load_mongo_settings
from backend.vendors.payments_adapter import (
    AMOUNT_MINOR_UNITS,
    CURRENCY,
    USER_ID,
    external_payment_match,
    month_label_expression,
    normalised_counterparty_expression,
    ref,
)
from backend.vendors.user_prices import USER_PRICES_COLLECTION, load_user_series

ALERTS_COLLECTION = "vendorAlerts"
ALERT_UNIQUE_KEY = ("source", "vendor", "currency", "month", "alertType")

PREDICTIVE = "predictive"
CONFIRMED = "confirmed"

PERSONAL_INCREASE = "personal_increase"
ABSOLUTE_COHORT = "absolute_cohort"

YEAR_OVER_YEAR = "year_over_year"
ROLLING = "rolling_3_month"


class DetectorConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_collection: str = "payments_seed_dev"
    stats_collection: str = STATS_COLLECTION
    alerts_collection: str = ALERTS_COLLECTION
    user_prices_collection: str = USER_PRICES_COLLECTION
    predictive_threshold: float = 0.08
    personal_increase_threshold: float = 0.08
    min_personal_increase_users: int = 2
    min_personal_increase_share: float = 0.0
    use_year_over_year: bool = True
    year_window_months: int = 1
    use_personal_increase: bool = True
    use_absolute_cohort: bool = True
    confirmed_threshold: float = 0.12
    baseline_months: int = 3
    min_cohort_users: int = 2
    baseline_match_tolerance: float = 0.02
    timezone: str = "Europe/Bucharest"
    rebuild: bool = True
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def price_cohort_pipeline(config: DetectorConfig) -> list[dict[str, Any]]:
    return [
        {"$match": external_payment_match()},
        {
            "$addFields": {
                "vendorNormalized": normalised_counterparty_expression(),
                "month": month_label_expression(config.timezone),
            }
        },
        {"$match": {"vendorNormalized": {"$ne": ""}}},
        {
            "$group": {
                "_id": {
                    "vendor": "$vendorNormalized",
                    "currency": ref(CURRENCY),
                    "month": "$month",
                    "amount": ref(AMOUNT_MINOR_UNITS),
                },
                "users": {"$addToSet": ref(USER_ID)},
                "transactionCount": {"$sum": 1},
            }
        },
        {
            "$project": {
                "_id": 1,
                "transactionCount": 1,
                "userCount": {"$size": "$users"},
            }
        },
        {"$match": {"userCount": {"$gte": config.min_cohort_users}}},
        {
            "$group": {
                "_id": {
                    "vendor": "$_id.vendor",
                    "currency": "$_id.currency",
                    "month": "$_id.month",
                },
                "cohorts": {
                    "$push": {
                        "amountMinorUnits": "$_id.amount",
                        "userCount": "$userCount",
                        "transactionCount": "$transactionCount",
                    }
                },
            }
        },
    ]


async def load_price_cohorts(
    db: Any, config: DetectorConfig
) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    cursor = await db[config.source_collection].aggregate(
        price_cohort_pipeline(config), allowDiskUse=True
    )
    rows = await cursor.to_list(length=None)
    return {
        (row["_id"]["vendor"], row["_id"]["currency"], row["_id"]["month"]): sorted(
            row["cohorts"], key=lambda cohort: cohort["amountMinorUnits"]
        )
        for row in rows
    }


async def load_monthly_stats(
    db: Any, config: DetectorConfig
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    rows = await db[config.stats_collection].find(
        {"source": config.source_collection}
    ).sort([("vendorNormalized", 1), ("currency", 1), ("month", 1)]).to_list(length=None)
    series: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        series.setdefault((row["vendorNormalized"], row["currency"]), []).append(row)
    for months in series.values():
        months.sort(key=lambda month: month["month"])
    return series


def baseline_from(window: list[dict[str, Any]]) -> int:
    return round(statistics.median(month["medianMinorUnits"] for month in window))


def month_offset(label: str, delta: int) -> str:
    total = int(label[:4]) * 12 + (int(label[5:7]) - 1) + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def year_ago_labels(label: str, window: int) -> list[str]:
    return [month_offset(label, -12 + offset) for offset in range(-window, window + 1)]


def resolve_baseline(
    prices: dict[str, int], label: str, config: DetectorConfig
) -> tuple[int, str, list[str]] | None:
    if config.use_year_over_year:
        candidates = [
            candidate
            for candidate in year_ago_labels(label, config.year_window_months)
            if candidate in prices
        ]
        if candidates:
            value = round(statistics.median(prices[key] for key in candidates))
            if value > 0:
                return value, YEAR_OVER_YEAR, candidates

    prior = sorted(key for key in prices if key < label)
    if len(prior) < config.baseline_months:
        return None
    window = prior[-config.baseline_months :]
    value = round(statistics.median(prices[key] for key in window))
    if value <= 0:
        return None
    return value, ROLLING, window


def percent_change(observed: int, baseline: int) -> float:
    return observed / baseline - 1.0


def already_announced(
    existing: list[dict[str, Any]],
    vendor: str,
    currency: str,
    baseline: int,
    observed: int,
    tolerance: float,
    alert_type: str = CONFIRMED,
) -> bool:
    for alert in existing:
        if alert["alertType"] != alert_type:
            continue
        if alert["vendor"] != vendor or alert["currency"] != currency:
            continue
        if baseline <= 0 or observed <= 0:
            continue
        if (
            abs(alert["baselineMinorUnits"] - baseline) / baseline <= tolerance
            and abs(alert["observedMinorUnits"] - observed) / observed <= tolerance
        ):
            return True
    return False


def personal_increase_cohort(
    user_series: dict[tuple[str, str, str], list[dict[str, Any]]],
    vendor: str,
    currency: str,
    month_label: str,
    config: DetectorConfig,
) -> tuple[list[dict[str, Any]], int]:
    flagged: list[dict[str, Any]] = []
    eligible = 0

    for (series_vendor, series_currency, user_id), months in user_series.items():
        if series_vendor != vendor or series_currency != currency:
            continue
        prices = {month["month"]: month["priceMinorUnits"] for month in months}
        if month_label not in prices:
            continue
        resolved = resolve_baseline(prices, month_label, config)
        if resolved is None:
            continue
        personal_baseline, method, window = resolved
        eligible += 1
        observed = prices[month_label]
        increase = percent_change(observed, personal_baseline)
        if increase >= config.personal_increase_threshold:
            flagged.append(
                {
                    "userId": user_id,
                    "baselineMinorUnits": personal_baseline,
                    "observedMinorUnits": observed,
                    "percentChange": increase,
                    "baselineMethod": method,
                    "baselineMonths": window,
                }
            )

    flagged.sort(key=lambda row: row["percentChange"], reverse=True)
    return flagged, eligible


def detect(
    series: dict[tuple[str, str], list[dict[str, Any]]],
    cohorts: dict[tuple[str, str, str], list[dict[str, Any]]],
    user_series: dict[tuple[str, str, str], list[dict[str, Any]]],
    existing: list[dict[str, Any]],
    config: DetectorConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    alerts: list[dict[str, Any]] = []
    known = list(existing)
    skipped: list[dict[str, Any]] = []

    for (vendor, currency), months in sorted(series.items()):
        for index, current in enumerate(months):
            vendor_prices = {
                month["month"]: month["medianMinorUnits"] for month in months
            }
            resolved = resolve_baseline(vendor_prices, current["month"], config)
            if resolved is None:
                skipped.append(
                    {
                        "vendor": vendor,
                        "currency": currency,
                        "month": current["month"],
                        "reason": "insufficient_history",
                        "monthsAvailable": index,
                    }
                )
                continue

            baseline, vendor_method, vendor_window = resolved
            window = [
                month for month in months if month["month"] in set(vendor_window)
            ]

            mechanisms: list[str] = []
            flagged: list[dict[str, Any]] = []
            eligible = 0
            if config.use_personal_increase:
                flagged, eligible = personal_increase_cohort(
                    user_series, vendor, currency, current["month"], config
                )
                share = len(flagged) / eligible if eligible else 0.0
                if (
                    len(flagged) >= config.min_personal_increase_users
                    and share >= config.min_personal_increase_share
                ):
                    mechanisms.append(PERSONAL_INCREASE)

            baseline_prices = {
                cohort["amountMinorUnits"]
                for month in window
                for cohort in cohorts.get((vendor, currency, month["month"]), [])
            }
            current_cohorts = cohorts.get((vendor, currency, current["month"]), [])
            novel = [
                cohort
                for cohort in current_cohorts
                if cohort["amountMinorUnits"] not in baseline_prices
                and cohort["amountMinorUnits"]
                >= baseline * (1.0 + config.predictive_threshold)
            ]
            if config.use_absolute_cohort and novel:
                mechanisms.append(ABSOLUTE_COHORT)

            if mechanisms:
                if PERSONAL_INCREASE in mechanisms:
                    observed = round(
                        statistics.median(row["observedMinorUnits"] for row in flagged)
                    )
                    predictive_baseline = round(
                        statistics.median(row["baselineMinorUnits"] for row in flagged)
                    )
                    observed_users = len(flagged)
                    personal_median: float | None = round(
                        statistics.median(row["percentChange"] for row in flagged), 6
                    )
                    method_counts: dict[str, int] = {}
                    for row in flagged:
                        method_counts[row["baselineMethod"]] = (
                            method_counts.get(row["baselineMethod"], 0) + 1
                        )
                    baseline_method = max(method_counts, key=lambda key: method_counts[key])
                    if len(method_counts) > 1:
                        baseline_method = "mixed"
                else:
                    leader = max(novel, key=lambda cohort: cohort["amountMinorUnits"])
                    observed = leader["amountMinorUnits"]
                    predictive_baseline = baseline
                    observed_users = leader["userCount"]
                    personal_median = None
                    method_counts = {vendor_method: 1}
                    baseline_method = vendor_method

                if already_announced(
                    known,
                    vendor,
                    currency,
                    predictive_baseline,
                    observed,
                    config.baseline_match_tolerance,
                    PREDICTIVE,
                ):
                    skipped.append(
                        {
                            "vendor": vendor,
                            "currency": currency,
                            "month": current["month"],
                            "reason": "already_predicted",
                            "baselineMinorUnits": predictive_baseline,
                            "observedMinorUnits": observed,
                        }
                    )
                    mechanisms = []

            if mechanisms:
                alert = {
                    "source": config.source_collection,
                    "vendor": vendor,
                    "currency": currency,
                    "month": current["month"],
                    "alertType": PREDICTIVE,
                    "signalMechanisms": mechanisms,
                    "baselineMinorUnits": predictive_baseline,
                    "observedMinorUnits": observed,
                    "percentChange": round(
                        percent_change(observed, predictive_baseline), 6
                    ),
                    "medianPersonalIncreasePct": personal_median,
                    "baselineMethod": baseline_method,
                    "baselineMethodCounts": method_counts,
                    "thresholdApplied": config.predictive_threshold,
                    "personalThresholdApplied": config.personal_increase_threshold,
                    "baselineMonths": [month["month"] for month in window],
                    "observedUserCount": observed_users,
                    "eligibleUserCount": eligible,
                    "monthUserCount": current["uniqueUserCount"],
                    "flaggedUserIds": [row["userId"] for row in flagged[:25]],
                    "createdAt": config.generated_at,
                }
                alerts.append(alert)
                known.append(alert)

            observed_median = current["medianMinorUnits"]
            if observed_median >= baseline * (1.0 + config.confirmed_threshold):
                if already_announced(
                    known,
                    vendor,
                    currency,
                    baseline,
                    observed_median,
                    config.baseline_match_tolerance,
                ):
                    skipped.append(
                        {
                            "vendor": vendor,
                            "currency": currency,
                            "month": current["month"],
                            "reason": "already_confirmed",
                            "baselineMinorUnits": baseline,
                            "observedMinorUnits": observed_median,
                        }
                    )
                    continue
                alert = {
                    "source": config.source_collection,
                    "vendor": vendor,
                    "currency": currency,
                    "month": current["month"],
                    "alertType": CONFIRMED,
                    "baselineMethod": vendor_method,
                    "baselineMinorUnits": baseline,
                    "observedMinorUnits": observed_median,
                    "percentChange": round(
                        percent_change(observed_median, baseline), 6
                    ),
                    "thresholdApplied": config.confirmed_threshold,
                    "baselineMonths": [month["month"] for month in window],
                    "observedUserCount": current["uniqueUserCount"],
                    "monthUserCount": current["uniqueUserCount"],
                    "createdAt": config.generated_at,
                }
                alerts.append(alert)
                known.append(alert)

    return alerts, skipped


async def ensure_alerts(db: Any, config: DetectorConfig) -> None:
    await db[config.alerts_collection].create_index(
        [(field, 1) for field in ALERT_UNIQUE_KEY],
        unique=True,
        name="vendor_alert_unique",
    )
    await db[config.alerts_collection].create_index([("source", 1), ("month", 1)])


async def run(
    db: Any, config: DetectorConfig
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    await ensure_alerts(db, config)
    if config.rebuild:
        await db[config.alerts_collection].delete_many(
            {"source": config.source_collection}
        )
        existing: list[dict[str, Any]] = []
    else:
        existing = await db[config.alerts_collection].find(
            {"source": config.source_collection}
        ).to_list(length=None)

    series = await load_monthly_stats(db, config)
    cohorts = await load_price_cohorts(db, config)
    user_series = await load_user_series(
        db, config.source_collection, config.user_prices_collection
    )
    alerts, skipped = detect(series, cohorts, user_series, existing, config)

    written = {"inserted": 0, "unchanged": 0}
    if alerts:
        result = await db[config.alerts_collection].bulk_write(
            [_upsert(alert) for alert in alerts],
            ordered=False,
        )
        written["inserted"] = result.upserted_count
        written["unchanged"] = len(alerts) - result.upserted_count
    return alerts, skipped, written


def _upsert(alert: dict[str, Any]) -> UpdateOne:
    key = {field: alert[field] for field in ALERT_UNIQUE_KEY}
    return UpdateOne(key, {"$set": alert}, upsert=True)


def money(minor_units: int) -> str:
    return f"{minor_units / 100:,.2f}"


def report(
    series: dict[tuple[str, str], list[dict[str, Any]]],
    alerts: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    written: dict[str, int],
    config: DetectorConfig,
) -> None:
    print(f"\nsource      : {config.source_collection}")
    print(f"stats       : {config.stats_collection}")
    print(f"alerts      : {config.alerts_collection}")
    active = []
    if config.use_personal_increase:
        gate = f"for >= {config.min_personal_increase_users} users"
        if config.min_personal_increase_share > 0:
            gate += f" and >= {config.min_personal_increase_share:.0%} of eligible"
        active.append(
            f"personal_increase >= {config.personal_increase_threshold:.0%} {gate}"
        )
    if config.use_absolute_cohort:
        active.append(
            f"absolute_cohort >= {config.predictive_threshold:.0%} "
            f"shared by >= {config.min_cohort_users} users"
        )
    print(f"predictive  : {'  |  '.join(active) or 'disabled'}")
    print(f"confirmed   : median >= {config.confirmed_threshold:.0%} over baseline")
    if config.use_year_over_year:
        print(
            f"baseline    : same month last year (+/-{config.year_window_months}), "
            f"falling back to the previous {config.baseline_months} months"
        )
    else:
        print(f"baseline    : median of the previous {config.baseline_months} months")
    print(
        f"alerts made : {len(alerts)} raised  "
        f"({written['inserted']} new, {written['unchanged']} already on record)\n"
    )

    by_vendor: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for alert in alerts:
        by_vendor.setdefault((alert["vendor"], alert["currency"]), []).append(alert)

    for (vendor, currency), months in sorted(series.items()):
        raised = sorted(
            by_vendor.get((vendor, currency), []),
            key=lambda alert: (alert["month"], alert["alertType"]),
        )
        span = f"{months[0]['month']}..{months[-1]['month']}"
        if not raised:
            print(f"{vendor} ({currency})  {span}   no alerts")
            continue
        print(f"{vendor} ({currency})  {span}")
        for alert in raised:
            share = ""
            if alert["alertType"] == PREDICTIVE:
                mechanisms = "+".join(
                    part.split("_")[0] for part in alert["signalMechanisms"]
                )
                share = (
                    f"  users {alert['observedUserCount']}"
                    f"/{alert['eligibleUserCount']} eligible"
                    f" of {alert['monthUserCount']}  via {mechanisms}"
                )
            print(
                f"  {alert['month']}  {alert['alertType'].upper():<10} "
                f"baseline {money(alert['baselineMinorUnits']):>9} -> "
                f"observed {money(alert['observedMinorUnits']):>9}  "
                f"{alert['percentChange']:+.2%}"
                f"{share}   [{alert['baselineMethod']}] "
                f"window {'/'.join(alert['baselineMonths'])}"
            )

    repeats = [
        row
        for row in skipped
        if row["reason"] in {"already_confirmed", "already_predicted"}
    ]
    suppressed = repeats
    thin = [row for row in skipped if row["reason"] == "insufficient_history"]
    print(f"\nsuppressed repeat alerts        : {len(suppressed)}")
    for row in suppressed:
        print(
            f"  {row['vendor']} {row['month']}  "
            f"{row['reason'].replace('already_', '')} would have repeated "
            f"{money(row['baselineMinorUnits'])} -> {money(row['observedMinorUnits'])}"
        )
    print(f"months skipped for thin history : {len(thin)}")


async def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="payments_seed_dev")
    parser.add_argument("--stats", default=STATS_COLLECTION)
    parser.add_argument("--alerts", default=ALERTS_COLLECTION)
    parser.add_argument("--predictive-threshold", type=float, default=0.08)
    parser.add_argument("--personal-threshold", type=float, default=0.08)
    parser.add_argument("--min-personal-users", type=int, default=2)
    parser.add_argument("--min-personal-share", type=float, default=0.0)
    parser.add_argument("--no-year-over-year", action="store_true")
    parser.add_argument("--year-window-months", type=int, default=1)
    parser.add_argument("--no-personal-increase", action="store_true")
    parser.add_argument("--no-absolute-cohort", action="store_true")
    parser.add_argument("--confirmed-threshold", type=float, default=0.12)
    parser.add_argument("--baseline-months", type=int, default=3)
    parser.add_argument("--min-cohort-users", type=int, default=2)
    parser.add_argument("--timezone", default="Europe/Bucharest")
    parser.add_argument("--no-rebuild", action="store_true")
    arguments = parser.parse_args()

    config = DetectorConfig(
        source_collection=arguments.source,
        stats_collection=arguments.stats,
        alerts_collection=arguments.alerts,
        predictive_threshold=arguments.predictive_threshold,
        personal_increase_threshold=arguments.personal_threshold,
        min_personal_increase_users=arguments.min_personal_users,
        min_personal_increase_share=arguments.min_personal_share,
        use_year_over_year=not arguments.no_year_over_year,
        year_window_months=arguments.year_window_months,
        use_personal_increase=not arguments.no_personal_increase,
        use_absolute_cohort=not arguments.no_absolute_cohort,
        confirmed_threshold=arguments.confirmed_threshold,
        baseline_months=arguments.baseline_months,
        min_cohort_users=arguments.min_cohort_users,
        timezone=arguments.timezone,
        rebuild=not arguments.no_rebuild,
    )

    uri, db_name = load_mongo_settings()
    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(
        uri, uuidRepresentation="standard", tz_aware=True, serverSelectionTimeoutMS=10000
    )
    try:
        db = client[db_name]
        alerts, skipped, written = await run(db, config)
        report(await load_monthly_stats(db, config), alerts, skipped, written, config)
    finally:
        await client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
