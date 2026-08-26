from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pymongo import AsyncMongoClient

from backend.vendors.payments_adapter import (
    AMOUNT_MINOR_UNITS,
    CATEGORY,
    COUNTERPARTY,
    CURRENCY,
    CREATED_AT,
    DIACRITIC_FOLDING,
    RAIL,
    USER_ID,
    external_payment_match,
    month_label_expression,
    month_start_expression,
    normalised_counterparty_expression,
    ref,
    warn_if_schema_changed,
)

STATS_COLLECTION = "vendorMonthlyStats"
UNIQUE_KEY = ("source", "vendorNormalized", "currency", "month")

class ExtractorConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_collection: str = "payments_seed_dev"
    target_collection: str = STATS_COLLECTION
    settled_statuses: tuple[str, ...] = ("posted",)
    internal_rails: tuple[str, ...] = ("internal",)
    timezone: str = "Europe/Bucharest"
    rebuild: bool = True
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def load_mongo_settings() -> tuple[str, str]:
    uri = os.environ.get("MONGO_URI")
    name = os.environ.get("MONGO_DB_NAME")
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
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
    return uri or "mongodb://172.16.64.44:27018/?replicaSet=rs-gemsbank", name or "gems"


def median_expression(field: str) -> dict[str, Any]:
    return {
        "$let": {
            "vars": {
                "sorted": {"$sortArray": {"input": f"${field}", "sortBy": 1}},
                "size": {"$size": f"${field}"},
            },
            "in": {
                "$cond": [
                    {"$eq": [{"$mod": ["$$size", 2]}, 1]},
                    {
                        "$arrayElemAt": [
                            "$$sorted",
                            {"$toInt": {"$floor": {"$divide": ["$$size", 2]}}},
                        ]
                    },
                    {
                        "$toInt": {
                            "$round": [
                                {
                                    "$avg": [
                                        {
                                            "$arrayElemAt": [
                                                "$$sorted",
                                                {
                                                    "$toInt": {
                                                        "$subtract": [
                                                            {"$divide": ["$$size", 2]},
                                                            1,
                                                        ]
                                                    }
                                                },
                                            ]
                                        },
                                        {
                                            "$arrayElemAt": [
                                                "$$sorted",
                                                {"$toInt": {"$divide": ["$$size", 2]}},
                                            ]
                                        },
                                    ]
                                },
                                0,
                            ]
                        }
                    },
                ]
            },
        }
    }


def build_pipeline(config: ExtractorConfig) -> list[dict[str, Any]]:
    return [
        {
            "$match": external_payment_match(
                config.settled_statuses, config.internal_rails
            )
        },
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
                    "month": "$month",
                },
                "monthStart": {"$first": "$monthStart"},
                "transactionCount": {"$sum": 1},
                "userIds": {"$addToSet": ref(USER_ID)},
                "amounts": {"$push": ref(AMOUNT_MINOR_UNITS)},
                "minMinorUnits": {"$min": ref(AMOUNT_MINOR_UNITS)},
                "maxMinorUnits": {"$max": ref(AMOUNT_MINOR_UNITS)},
                "meanMinorUnits": {"$avg": ref(AMOUNT_MINOR_UNITS)},
                "counterpartyVariants": {"$addToSet": ref(COUNTERPARTY)},
                "categories": {"$addToSet": ref(CATEGORY)},
                "rails": {"$addToSet": ref(RAIL)},
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
                "month": "$_id.month",
                "monthStart": 1,
                "transactionCount": 1,
                "uniqueUserCount": {"$size": "$userIds"},
                "medianMinorUnits": median_expression("amounts"),
                "minMinorUnits": 1,
                "maxMinorUnits": 1,
                "meanMinorUnits": {"$toInt": {"$round": ["$meanMinorUnits", 0]}},
                "counterpartyVariants": {"$sortArray": {"input": "$counterpartyVariants", "sortBy": 1}},
                "categories": {"$sortArray": {"input": "$categories", "sortBy": 1}},
                "rails": {"$sortArray": {"input": "$rails", "sortBy": 1}},
                "firstSeenAt": 1,
                "lastSeenAt": 1,
                "generatedAt": {"$literal": config.generated_at},
            }
        },
        {"$sort": {"vendorNormalized": 1, "currency": 1, "month": 1}},
        {
            "$merge": {
                "into": config.target_collection,
                "on": list(UNIQUE_KEY),
                "whenMatched": "replace",
                "whenNotMatched": "insert",
            }
        },
    ]


async def ensure_target(db: Any, config: ExtractorConfig) -> None:
    await db[config.target_collection].create_index(
        [(field, 1) for field in UNIQUE_KEY], unique=True, name="vendor_month_unique"
    )
    await db[config.target_collection].create_index([("source", 1), ("monthStart", 1)])


async def run(db: Any, config: ExtractorConfig) -> list[dict[str, Any]]:
    await warn_if_schema_changed(db, config.source_collection)
    await ensure_target(db, config)
    if config.rebuild:
        await db[config.target_collection].delete_many(
            {"source": config.source_collection}
        )
    await (
        await db[config.source_collection].aggregate(build_pipeline(config))
    ).to_list(length=None)
    cursor = await db[config.target_collection].find(
        {"source": config.source_collection}
    ).sort([("vendorNormalized", 1), ("currency", 1), ("month", 1)]).to_list(length=None)
    return cursor


def money(minor_units: int) -> str:
    return f"{minor_units / 100:,.2f}"


def report(rows: list[dict[str, Any]], config: ExtractorConfig) -> None:
    print(f"\nsource     : {config.source_collection}")
    print(f"target     : {config.target_collection}")
    print(f"timezone   : {config.timezone}")
    print(f"rows       : {len(rows)}")

    vendors: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        vendors.setdefault((row["vendorNormalized"], row["currency"]), []).append(row)

    print(f"vendors    : {len(vendors)}\n")

    header = (
        f"{'vendor':<24}{'cur':<5}{'months':>7}{'txns':>6}{'users':>7}"
        f"{'median avg':>12}{'min':>10}{'max':>10}"
    )
    print(header)
    print("-" * len(header))
    for (vendor, currency), months in sorted(vendors.items()):
        medians = [month["medianMinorUnits"] for month in months]
        print(
            f"{vendor:<24}{currency:<5}{len(months):>7}"
            f"{sum(month['transactionCount'] for month in months):>6}"
            f"{max(month['uniqueUserCount'] for month in months):>7}"
            f"{money(round(sum(medians) / len(medians))):>12}"
            f"{money(min(month['minMinorUnits'] for month in months)):>10}"
            f"{money(max(month['maxMinorUnits'] for month in months)):>10}"
        )

    for (vendor, currency), months in sorted(vendors.items()):
        print(f"\n{vendor} ({currency})")
        for month in sorted(months, key=lambda row: row["month"]):
            spread = month["maxMinorUnits"] - month["minMinorUnits"]
            print(
                f"  {month['month']}  txns {month['transactionCount']:>3}  "
                f"users {month['uniqueUserCount']:>3}  "
                f"median {money(month['medianMinorUnits']):>9}  "
                f"min {money(month['minMinorUnits']):>9}  "
                f"max {money(month['maxMinorUnits']):>9}  "
                f"spread {money(spread):>9}"
            )
        variants = sorted({name for month in months for name in month["counterpartyVariants"]})
        if len(variants) > 1:
            print(f"  raw counterparty variants folded: {variants}")


async def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="payments_seed_dev")
    parser.add_argument("--target", default=STATS_COLLECTION)
    parser.add_argument("--timezone", default="Europe/Bucharest")
    parser.add_argument("--status", action="append", default=None)
    parser.add_argument("--no-rebuild", action="store_true")
    arguments = parser.parse_args()

    config = ExtractorConfig(
        source_collection=arguments.source,
        target_collection=arguments.target,
        timezone=arguments.timezone,
        settled_statuses=tuple(arguments.status or ("posted",)),
        rebuild=not arguments.no_rebuild,
    )

    uri, db_name = load_mongo_settings()
    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(
        uri, uuidRepresentation="standard", tz_aware=True, serverSelectionTimeoutMS=10000
    )
    try:
        rows = await run(client[db_name], config)
        report(rows, config)
    finally:
        await client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
