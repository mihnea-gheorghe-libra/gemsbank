from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pymongo import AsyncMongoClient

from backend.vendors.extractor import load_mongo_settings, median_expression
from backend.vendors.payments_adapter import (
    AMOUNT_MINOR_UNITS,
    CREATED_AT,
    CURRENCY,
    USER_ID,
    external_payment_match,
    month_label_expression,
    month_start_expression,
    normalised_counterparty_expression,
    ref,
    warn_if_schema_changed,
)

USER_PRICES_COLLECTION = "vendorUserMonthlyPrices"
USER_PRICES_UNIQUE_KEY = (
    "source",
    "vendorNormalized",
    "currency",
    "userId",
    "month",
)


class UserPriceConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_collection: str = "payments_seed_dev"
    target_collection: str = USER_PRICES_COLLECTION
    timezone: str = "Europe/Bucharest"
    history_months: int | None = None
    rebuild: bool = True
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def cutoff_for(config: UserPriceConfig) -> datetime | None:
    if config.history_months is None:
        return None
    anchor = config.generated_at
    total = anchor.year * 12 + (anchor.month - 1) - config.history_months
    return datetime(total // 12, total % 12 + 1, 1, tzinfo=UTC)


def build_pipeline(config: UserPriceConfig) -> list[dict[str, Any]]:
    match = dict(external_payment_match())
    cutoff = cutoff_for(config)
    if cutoff is not None:
        match[CREATED_AT] = {"$gte": cutoff}

    return [
        {"$match": match},
        {
            "$addFields": {
                "vendorNormalized": normalised_counterparty_expression(),
                "monthStart": month_start_expression(config.timezone),
                "month": month_label_expression(config.timezone),
            }
        },
        {"$match": {"vendorNormalized": {"$ne": ""}}},
        {
            "$group": {
                "_id": {
                    "vendorNormalized": "$vendorNormalized",
                    "currency": ref(CURRENCY),
                    "userId": ref(USER_ID),
                    "month": "$month",
                },
                "monthStart": {"$first": "$monthStart"},
                "amounts": {"$push": ref(AMOUNT_MINOR_UNITS)},
                "transactionCount": {"$sum": 1},
                "totalMinorUnits": {"$sum": ref(AMOUNT_MINOR_UNITS)},
                "minMinorUnits": {"$min": ref(AMOUNT_MINOR_UNITS)},
                "maxMinorUnits": {"$max": ref(AMOUNT_MINOR_UNITS)},
                "firstSeenAt": {"$min": ref(CREATED_AT)},
                "lastSeenAt": {"$max": ref(CREATED_AT)},
            }
        },
        {
            "$project": {
                "_id": 0,
                "source": {"$literal": config.source_collection},
                "vendorNormalized": "$_id.vendorNormalized",
                "currency": "$_id.currency",
                "userId": "$_id.userId",
                "month": "$_id.month",
                "monthStart": 1,
                "priceMinorUnits": median_expression("amounts"),
                "transactionCount": 1,
                "totalMinorUnits": 1,
                "minMinorUnits": 1,
                "maxMinorUnits": 1,
                "firstSeenAt": 1,
                "lastSeenAt": 1,
                "generatedAt": {"$literal": config.generated_at},
            }
        },
        {"$sort": {"vendorNormalized": 1, "userId": 1, "month": 1}},
        {
            "$merge": {
                "into": config.target_collection,
                "on": list(USER_PRICES_UNIQUE_KEY),
                "whenMatched": "replace",
                "whenNotMatched": "insert",
            }
        },
    ]


async def ensure_target(db: Any, config: UserPriceConfig) -> None:
    await db[config.target_collection].create_index(
        [(field, 1) for field in USER_PRICES_UNIQUE_KEY],
        unique=True,
        name="vendor_user_month_unique",
    )
    await db[config.target_collection].create_index(
        [("source", 1), ("vendorNormalized", 1), ("month", 1)]
    )


async def run(db: Any, config: UserPriceConfig) -> int:
    await warn_if_schema_changed(db, config.source_collection)
    await ensure_target(db, config)
    if config.rebuild:
        await db[config.target_collection].delete_many(
            {"source": config.source_collection}
        )
    await (
        await db[config.source_collection].aggregate(
            build_pipeline(config), allowDiskUse=True
        )
    ).to_list(length=None)
    return await db[config.target_collection].count_documents(
        {"source": config.source_collection}
    )


async def load_user_series(
    db: Any, source_collection: str, target_collection: str = USER_PRICES_COLLECTION
) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    rows = await db[target_collection].find({"source": source_collection}).to_list(
        length=None
    )
    series: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (row["vendorNormalized"], row["currency"], row["userId"])
        series.setdefault(key, []).append(row)
    for months in series.values():
        months.sort(key=lambda month: month["month"])
    return series


async def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="payments_seed_dev")
    parser.add_argument("--target", default=USER_PRICES_COLLECTION)
    parser.add_argument("--timezone", default="Europe/Bucharest")
    parser.add_argument("--history-months", type=int, default=None)
    parser.add_argument("--no-rebuild", action="store_true")
    arguments = parser.parse_args()

    config = UserPriceConfig(
        source_collection=arguments.source,
        target_collection=arguments.target,
        timezone=arguments.timezone,
        history_months=arguments.history_months,
        rebuild=not arguments.no_rebuild,
    )

    uri, db_name = load_mongo_settings()
    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(
        uri, uuidRepresentation="standard", tz_aware=True, serverSelectionTimeoutMS=10000
    )
    try:
        db = client[db_name]
        written = await run(db, config)
        series = await load_user_series(db, config.source_collection, config.target_collection)
        multi = [
            row
            for months in series.values()
            for row in months
            if row["transactionCount"] > 1
        ]
        print(f"source   : {config.source_collection}")
        print(f"target   : {config.target_collection}")
        print(f"rows     : {written}")
        print(f"tracked  : {len(series)} (vendor, currency, user) series")
        print(f"months with more than one payment: {len(multi)}")
    finally:
        await client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
