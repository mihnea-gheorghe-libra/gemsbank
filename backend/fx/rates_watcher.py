from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pymongo import AsyncMongoClient, UpdateOne

from backend.config import settings
from backend.fx.adapters import (
    assumptions_summary,
    currency_holdings,
    held_foreign_currencies,
    missing_collections,
    warn_if_schema_changed,
)
from backend.fx.bnr_feed import SOURCE, DailyRate, Feed, fetch_feed
from backend.fx.signals import (
    NOTIFICATION_UNIQUE_KEY,
    NOTIFICATIONS_COLLECTION,
    RATE_UNIQUE_KEY,
    RATES_COLLECTION,
    SIGNAL_UNIQUE_KEY,
    SIGNALS_COLLECTION,
    SignalRule,
    build_notifications,
    build_signal,
    rate_record,
)
from backend.fx.validation import BASE_CURRENCY, rate_text
from backend.ledger.validation import SUPPORTED_CURRENCIES

MINIMUM_CURRENCIES = tuple(sorted(SUPPORTED_CURRENCIES - {BASE_CURRENCY}))


def load_mongo_settings() -> tuple[str, str]:
    uri = os.environ.get("MONGO_URI")
    name = os.environ.get("MONGO_DB_NAME")
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key == "MONGO_URI" and not uri:
                uri = value
            if key == "MONGO_DB_NAME" and not name:
                name = value
    return uri or settings.mongo_uri, name or settings.mongo_db_name


class WatcherConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str = SOURCE
    feed_url: str = settings.bnr_fx_feed_url
    history_feed_url: str = settings.bnr_fx_history_feed_url
    rates_collection: str = RATES_COLLECTION
    signals_collection: str = SIGNALS_COLLECTION
    notifications_collection: str = NOTIFICATIONS_COLLECTION
    currencies: tuple[str, ...] = ()
    backfill_history: bool = False
    request_timeout_seconds: float = 15.0
    dry_run: bool = False
    rule: SignalRule = Field(default_factory=SignalRule)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


async def ensure_collections(db: Any, config: WatcherConfig) -> None:
    await db[config.rates_collection].create_index(
        [(field, 1) for field in RATE_UNIQUE_KEY], unique=True, name="fx_rate_unique"
    )
    await db[config.rates_collection].create_index([("currency", 1), ("date", -1)])
    await db[config.signals_collection].create_index(
        [(field, 1) for field in SIGNAL_UNIQUE_KEY], unique=True, name="fx_signal_unique"
    )
    await db[config.signals_collection].create_index([("currency", 1), ("date", -1)])
    await db[config.notifications_collection].create_index(
        [(field, 1) for field in NOTIFICATION_UNIQUE_KEY],
        unique=True,
        name="fx_notification_unique",
    )
    await db[config.notifications_collection].create_index(
        [("userId", 1), ("signalDate", -1)]
    )


async def resolve_currencies(
    db: Any, config: WatcherConfig
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    from_accounts = await held_foreign_currencies(db)
    if config.currencies:
        return tuple(sorted({value.upper() for value in config.currencies})), from_accounts
    selected = tuple(sorted(set(from_accounts) | set(MINIMUM_CURRENCIES)))
    return selected, from_accounts


def upsert(collection_key: tuple[str, ...], record: dict[str, Any]) -> UpdateOne:
    return UpdateOne(
        {field: record[field] for field in collection_key},
        {"$set": record},
        upsert=True,
    )


def rate_records(
    rates: tuple[DailyRate, ...], source: str
) -> list[dict[str, Any]]:
    return [
        rate_record(rate.currency, rate.date, rate.rate_micro, rate.multiplier, source)
        for rate in rates
    ]


async def store_rates(
    db: Any, config: WatcherConfig, records: list[dict[str, Any]]
) -> int:
    if not records or config.dry_run:
        return 0
    result = await db[config.rates_collection].bulk_write(
        [upsert(RATE_UNIQUE_KEY, record) for record in records], ordered=False
    )
    return int(result.upserted_count)


async def load_history(
    db: Any, config: WatcherConfig, currencies: tuple[str, ...]
) -> dict[str, dict[str, int]]:
    rows = (
        await db[config.rates_collection]
        .find(
            {"source": config.source, "currency": {"$in": list(currencies)}},
            {"currency": 1, "date": 1, "rateMicroUnits": 1, "_id": 0},
        )
        .to_list(length=None)
    )
    history: dict[str, dict[str, int]] = {currency: {} for currency in currencies}
    for row in rows:
        history.setdefault(row["currency"], {})[row["date"]] = int(row["rateMicroUnits"])
    return history


async def load_notified(
    db: Any, config: WatcherConfig
) -> dict[tuple[str, str], dict[str, Any]]:
    rows = (
        await db[config.notifications_collection]
        .find({"source": config.source})
        .sort([("signalDate", -1)])
        .to_list(length=None)
    )
    newest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        newest.setdefault((row["userId"], row["currency"]), row)
    return newest


async def run(db: Any, config: WatcherConfig) -> dict[str, Any]:
    schema = await warn_if_schema_changed(db)
    absent = missing_collections(schema)
    if absent:
        return {"fatal": f"missing_collections:{','.join(absent)}"}

    await ensure_collections(db, config)
    currencies, from_accounts = await resolve_currencies(db, config)

    feeds: list[tuple[str, Feed]] = []
    feed_errors: list[dict[str, str]] = []

    if config.backfill_history:
        feed, error = await fetch_feed(
            config.history_feed_url, config.request_timeout_seconds
        )
        if error or feed is None:
            feed_errors.append({"url": config.history_feed_url, "reason": error or "empty"})
        else:
            feeds.append((config.history_feed_url, feed))

    feed, error = await fetch_feed(config.feed_url, config.request_timeout_seconds)
    if error or feed is None:
        feed_errors.append({"url": config.feed_url, "reason": error or "empty"})
    else:
        feeds.append((config.feed_url, feed))

    if not feeds:
        return {"fatal": "no_feed_reachable", "feed_errors": feed_errors}

    stored: list[dict[str, Any]] = []
    for _url, parsed in feeds:
        stored += rate_records(parsed.for_currencies(currencies), config.source)

    upserted = await store_rates(db, config, stored)
    history = await load_history(db, config, currencies)

    latest_feed = feeds[-1][1]
    latest_date = latest_feed.latest_date()
    current: dict[str, DailyRate] = {
        rate.currency: rate
        for rate in latest_feed.for_currencies(currencies)
        if rate.date == latest_date
    }

    signals: list[dict[str, Any]] = []
    signal_skips: list[dict[str, Any]] = []
    for currency in currencies:
        rate = current.get(currency)
        if rate is None:
            signal_skips.append({"currency": currency, "reason": "absent_from_feed"})
            continue
        baseline_pool = {
            day: value
            for day, value in history.get(currency, {}).items()
            if day < rate.date
        }
        signal, reason = build_signal(
            currency, rate.date, rate.rate_micro, baseline_pool, config.rule
        )
        if signal is None:
            signal_skips.append({"currency": currency, "reason": reason})
            continue
        signals.append(signal)

    if signals and not config.dry_run:
        await db[config.signals_collection].bulk_write(
            [upsert(SIGNAL_UNIQUE_KEY, signal) for signal in signals], ordered=False
        )

    holdings = await currency_holdings(db, currencies)
    already_notified = await load_notified(db, config)
    notifications, notification_skips = build_notifications(
        signals, holdings, already_notified, config.rule
    )

    if notifications and not config.dry_run:
        await db[config.notifications_collection].bulk_write(
            [upsert(NOTIFICATION_UNIQUE_KEY, row) for row in notifications],
            ordered=False,
        )

    return {
        "currencies": currencies,
        "currencies_from_accounts": from_accounts,
        "feeds": [
            {"url": url, "dates": parsed.dates(), "currencies": len(parsed.currencies())}
            for url, parsed in feeds
        ],
        "feed_errors": feed_errors,
        "latest_date": latest_date,
        "publishing_date": latest_feed.publishing_date,
        "current": current,
        "rate_rows_written": len(stored),
        "rate_rows_new": upserted,
        "history_depth": {
            currency: len(history.get(currency, {})) for currency in currencies
        },
        "signals": signals,
        "signal_skips": signal_skips,
        "holdings": holdings,
        "notifications": notifications,
        "notification_skips": notification_skips,
    }


def report(outcome: dict[str, Any], config: WatcherConfig) -> None:
    if outcome.get("fatal"):
        print(f"\nfatal        : {outcome['fatal']}")
        for row in outcome.get("feed_errors", []):
            print(f"  {row['url']}  {row['reason']}")
        return

    print(f"\nsource       : {config.source}")
    print(f"threshold    : {config.rule.threshold_percent}% over {config.rule.baseline_days} days")
    print(f"repeat guard : {config.rule.repeat_rate_tolerance_percent}%")
    print(f"min balance  : {config.rule.min_balance_minor_units} minor units")
    print(f"mode         : {'dry run, nothing written' if config.dry_run else 'writing'}")

    for row in outcome["feeds"]:
        span = f"{row['dates'][0]}..{row['dates'][-1]}" if row["dates"] else "empty"
        print(f"feed         : {row['url']}  {row['currencies']} currencies  {span}")
    for row in outcome["feed_errors"]:
        print(f"feed error   : {row['url']}  {row['reason']}")

    print(f"published    : {outcome['publishing_date']}  latest cube {outcome['latest_date']}")
    print(
        f"currencies   : tracked {','.join(outcome['currencies'])}  "
        f"held in accounts {','.join(outcome['currencies_from_accounts']) or 'none'}"
    )
    print(
        f"fxRatesDaily : {outcome['rate_rows_written']} rows upserted, "
        f"{outcome['rate_rows_new']} new"
    )

    header = f"{'currency':<10}{'rate':>12}{'history':>9}{'signal':>28}"
    print()
    print(header)
    print("-" * len(header))
    by_currency = {signal["currency"]: signal for signal in outcome["signals"]}
    skips = {row["currency"]: row["reason"] for row in outcome["signal_skips"]}
    for currency in outcome["currencies"]:
        rate = outcome["current"].get(currency)
        value = rate_text(rate.rate_micro) if rate else "-"
        signal = by_currency.get(currency)
        if signal:
            verdict = (
                f"{signal['direction']} {signal['changePercent']:+.2f}% "
                f"vs {signal['baselineDate']}"
            )
        else:
            verdict = skips.get(currency, "-")
        print(
            f"{currency:<10}{value:>12}"
            f"{outcome['history_depth'].get(currency, 0):>9}{verdict:>28}"
        )

    print(f"\nholdings with a balance in a tracked currency: {len(outcome['holdings'])}")
    for holding in outcome["holdings"]:
        print(
            f"  {holding['userId']}  {holding['currency']}  "
            f"{holding['amountMinorUnits']} minor units  "
            f"{len(holding['accountIds'])} account(s)"
        )

    print(f"\nfxSignals written      : {len(outcome['signals'])}")
    print(f"fxNotifications written: {len(outcome['notifications'])}")
    for row in outcome["notifications"]:
        print(f"  {row['userId']}  {row['currency']}  {row['shortText']}")
        print(f"     {row['longText']}")
        print(f"     {row['longTextEn']}")

    if outcome["notification_skips"]:
        print("\nnotification skips:")
        for row in outcome["notification_skips"]:
            print(
                f"  {row['currency']:<6} {row['signalDate']:<12} "
                f"{row['userId']!s:<40} {row['reason']}"
            )


async def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=SOURCE)
    parser.add_argument("--currency", action="append", default=None)
    parser.add_argument("--feed-url", default=settings.bnr_fx_feed_url)
    parser.add_argument("--history-feed-url", default=settings.bnr_fx_history_feed_url)
    parser.add_argument("--source-page-url", default=settings.bnr_fx_source_page_url)
    parser.add_argument("--threshold-percent", type=float, default=settings.fx_signal_threshold_percent)
    parser.add_argument("--baseline-days", type=int, default=settings.fx_baseline_days)
    parser.add_argument(
        "--repeat-tolerance-percent",
        type=float,
        default=settings.fx_repeat_rate_tolerance_percent,
    )
    parser.add_argument("--min-balance-minor-units", type=int, default=1)
    parser.add_argument("--backfill-history", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--explain-source", action="store_true")
    arguments = parser.parse_args()

    if arguments.explain_source:
        print(assumptions_summary())
        return 0

    config = WatcherConfig(
        source=arguments.source,
        feed_url=arguments.feed_url,
        history_feed_url=arguments.history_feed_url,
        currencies=tuple(arguments.currency or ()),
        backfill_history=arguments.backfill_history,
        dry_run=arguments.dry_run,
        rule=SignalRule(
            source=arguments.source,
            source_url=arguments.source_page_url,
            baseline_days=arguments.baseline_days,
            threshold_percent=arguments.threshold_percent,
            repeat_rate_tolerance_percent=arguments.repeat_tolerance_percent,
            min_balance_minor_units=arguments.min_balance_minor_units,
        ),
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
    return 2 if outcome.get("fatal") else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
