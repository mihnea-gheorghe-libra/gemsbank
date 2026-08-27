from __future__ import annotations

import argparse
import asyncio
import math
import os
import random
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pymongo import AsyncMongoClient
from pymongo.errors import CollectionInvalid

SOURCE_COLLECTION = "payments"
EXTRA_RAILS = ("card", "direct_debit")

RNG_SEED = 20260825
USER_COUNT = 18
NETFLIX_COHORT_SIZE = 15
NETFLIX_CANARY_SHARE = 0.20
NETFLIX_PRICE_BEFORE = 4900
NETFLIX_PRICE_AFTER = 5900

Rail = Literal["card", "direct_debit"]


class Vendor:
    def __init__(
        self,
        key: str,
        name: str,
        category: str,
        rail: Rail,
        bank_code: str,
        base_minor: int,
        jitter: float,
        reference: str,
        seasonal_amplitude: float = 0.0,
        tariff_increase: float = 0.0,
    ) -> None:
        self.key = key
        self.name = name
        self.category = category
        self.rail = rail
        self.bank_code = bank_code
        self.base_minor = base_minor
        self.jitter = jitter
        self.reference = reference
        self.seasonal_amplitude = seasonal_amplitude
        self.tariff_increase = tariff_increase


VENDORS = (
    Vendor(
        "netflix",
        "Netflix",
        "entertainment",
        "card",
        "BTRL",
        NETFLIX_PRICE_BEFORE,
        0.0,
        "Netflix abonament lunar",
    ),
    Vendor(
        "enel",
        "Enel Energie",
        "utilities",
        "direct_debit",
        "RNCB",
        18500,
        0.03,
        "Enel factura energie",
        seasonal_amplitude=0.35,
        tariff_increase=0.22,
    ),
    Vendor(
        "digi",
        "Digi Communications",
        "utilities",
        "direct_debit",
        "BRDE",
        4000,
        0.02,
        "Digi internet si TV",
        seasonal_amplitude=0.25,
    ),
    Vendor(
        "kaufland",
        "Kaufland Baneasa",
        "groceries",
        "card",
        "INGB",
        27000,
        0.03,
        "Kaufland cumparaturi",
    ),
    Vendor(
        "omv",
        "OMV Petrom",
        "transport",
        "card",
        "RZBR",
        22000,
        0.03,
        "OMV alimentare carburant",
    ),
)

SEASONAL_KEYS = tuple(
    vendor.key for vendor in VENDORS if vendor.seasonal_amplitude > 0.0
)

REAL_USER_VENDOR_KEYS = ("netflix", "enel", "digi")


class RealUser:
    def __init__(self, username: str, user_id: str, account_id: str) -> None:
        self.username = username
        self.user_id = user_id
        self.account_id = account_id


class SeedConfig:
    def __init__(
        self,
        collection: str,
        seed_batch: str,
        period_months: int,
        increase_month_index: int,
        seasonal: bool,
        real_users: tuple[RealUser, ...] = (),
        tariff_increase_keys: tuple[str, ...] = (),
    ) -> None:
        self.collection = collection
        self.seed_batch = seed_batch
        self.period_months = period_months
        self.increase_month_index = increase_month_index
        self.seasonal = seasonal
        self.real_users = real_users
        self.tariff_increase_keys = tariff_increase_keys


def load_mongo_settings() -> tuple[str, str]:
    uri = os.environ.get("MONGO_URI")
    name = os.environ.get("MONGO_DB_NAME")
    env_path = Path(__file__).resolve().parent.parent / ".env"
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


def uuid7_from(rng: random.Random, unix_ms: int) -> str:
    value = bytearray(16)
    value[0:6] = unix_ms.to_bytes(6, "big")
    value[6:16] = bytes(rng.getrandbits(8) for _ in range(10))
    value[6] = (value[6] & 0x0F) | 0x70
    value[8] = (value[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(value)))


def iban_ro(bank_code: str, account_digits: str) -> str:
    bban = f"{bank_code}{account_digits}"
    numeric = "".join(
        str(ord(char) - 55) if char.isalpha() else char for char in f"{bban}RO00"
    )
    check = 98 - (int(numeric) % 97)
    return f"RO{check:02d}{bban}"


def seasonal_multiplier(amplitude: float, calendar_month: int) -> float:
    if amplitude == 0.0:
        return 1.0
    phase = 2.0 * math.pi * (calendar_month - 1) / 12.0
    return 1.0 + amplitude * (1.0 + math.cos(phase)) / 2.0


def month_starts(count: int, now: datetime) -> list[datetime]:
    last_complete = datetime(now.year, now.month, 1, tzinfo=UTC) - timedelta(days=1)
    year, month = last_complete.year, last_complete.month
    months: list[datetime] = []
    for _ in range(count):
        months.append(datetime(year, month, 1, tzinfo=UTC))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(months))


def netflix_switch_schedule(
    rng: random.Random, cohort: list[str], increase_month_index: int
) -> dict[str, int]:
    shuffled = list(cohort)
    rng.shuffle(shuffled)
    canary_size = max(1, round(len(shuffled) * NETFLIX_CANARY_SHARE))
    canary = shuffled[:canary_size]
    rest = shuffled[canary_size:]
    half = len(rest) // 2
    waves = {
        increase_month_index: canary,
        increase_month_index + 1: rest[:half],
        increase_month_index + 2: rest[half:],
    }
    return {user_id: index for index, users in waves.items() for user_id in users}


def jittered(rng: random.Random, base: int, jitter: float) -> int:
    if jitter == 0.0:
        return base
    return max(1, round(base * (1.0 + rng.uniform(-jitter, jitter))))


async def clone_validator(db: Any) -> dict[str, Any]:
    cursor = await db.list_collections(filter={"name": SOURCE_COLLECTION})
    entries = await cursor.to_list(length=1)
    if not entries:
        raise SystemExit(
            f"collection '{SOURCE_COLLECTION}' not found; apply ops/004_payments_ledger_schema.js first"
        )
    validator = entries[0].get("options", {}).get("validator")
    if not validator:
        raise SystemExit(f"collection '{SOURCE_COLLECTION}' has no validator to clone")
    rail = validator["$jsonSchema"]["properties"]["rail"]
    existing = list(rail.get("enum", ()))
    rail["enum"] = existing + [value for value in EXTRA_RAILS if value not in existing]
    return validator


async def resolve_real_users(db: Any, usernames: tuple[str, ...]) -> tuple[RealUser, ...]:
    resolved: list[RealUser] = []
    for username in usernames:
        user = await db["users"].find_one({"username": username.strip()})
        if not user or not user.get("_id"):
            raise SystemExit(
                f"user '{username}' not found in the 'users' collection; "
                "seed real transactions only for accounts that actually exist"
            )
        user_id = str(user["_id"])
        account = await db["accounts"].find_one(
            {"userId": user_id, "currency": "RON", "kind": "current"}
        ) or await db["accounts"].find_one({"userId": user_id, "currency": "RON"})
        if not account or not account.get("_id"):
            raise SystemExit(
                f"user '{username}' has no RON account to debit; "
                "open one before seeding their vendor history"
            )
        resolved.append(RealUser(username, user_id, str(account["_id"])))
    return tuple(resolved)


async def ensure_collection(
    db: Any, validator: dict[str, Any], config: SeedConfig
) -> None:
    try:
        await db.create_collection(config.collection)
    except CollectionInvalid:
        pass
    await db.command(
        {
            "collMod": config.collection,
            "validator": validator,
            "validationLevel": "strict",
            "validationAction": "error",
        }
    )
    collection = db[config.collection]
    await collection.create_index([("userId", 1), ("createdAt", -1)])
    await collection.create_index([("counterparty", 1), ("createdAt", 1)])
    await collection.create_index([("seedBatch", 1)])


def build_documents(
    now: datetime, config: SeedConfig
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rng = random.Random(RNG_SEED)
    base_ms = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp() * 1000)

    user_ids = [uuid7_from(rng, base_ms + index) for index in range(USER_COUNT)]
    accounts = {
        user_id: uuid7_from(rng, base_ms + 1000 + index)
        for index, user_id in enumerate(user_ids)
    }
    vendor_ibans = {
        vendor.key: iban_ro(vendor.bank_code, f"{rng.randrange(10**16):016d}")
        for vendor in VENDORS
    }

    netflix_cohort = user_ids[:NETFLIX_COHORT_SIZE]
    switch_month = netflix_switch_schedule(
        rng, netflix_cohort, config.increase_month_index
    )

    others = [vendor for vendor in VENDORS if vendor.key != "netflix"]
    netflix = next(vendor for vendor in VENDORS if vendor.key == "netflix")
    subscriptions: dict[str, list[Vendor]] = {}
    for user_id in user_ids:
        chosen = [netflix] if user_id in netflix_cohort else []
        chosen += rng.sample(others, rng.randint(2, 4))
        subscriptions[user_id] = sorted(chosen, key=lambda vendor: vendor.key)

    billing_days = {
        (user_id, vendor.key): rng.randint(1, 28)
        for user_id in user_ids
        for vendor in subscriptions[user_id]
    }

    real_rng = random.Random(RNG_SEED + 1)
    real_vendors = sorted(
        (vendor for vendor in VENDORS if vendor.key in REAL_USER_VENDOR_KEYS),
        key=lambda vendor: vendor.key,
    )
    for real_user in config.real_users:
        user_ids.append(real_user.user_id)
        accounts[real_user.user_id] = real_user.account_id
        subscriptions[real_user.user_id] = list(real_vendors)
        switch_month[real_user.user_id] = config.increase_month_index
        for vendor in real_vendors:
            billing_days[(real_user.user_id, vendor.key)] = real_rng.randint(1, 28)

    real_ids = {real_user.user_id for real_user in config.real_users}

    documents: list[dict[str, Any]] = []
    for month_index, month in enumerate(month_starts(config.period_months, now)):
        for user_id in user_ids:
            draw = real_rng if user_id in real_ids else rng
            for vendor in subscriptions[user_id]:
                posted_at = month.replace(
                    day=billing_days[(user_id, vendor.key)]
                ) + timedelta(
                    hours=draw.randint(6, 21),
                    minutes=draw.randint(0, 59),
                    seconds=draw.randint(0, 59),
                )
                multiplier = (
                    seasonal_multiplier(vendor.seasonal_amplitude, month.month)
                    if config.seasonal
                    else 1.0
                )
                if vendor.key == "netflix":
                    switched = month_index >= switch_month[user_id]
                    amount = NETFLIX_PRICE_AFTER if switched else NETFLIX_PRICE_BEFORE
                    tier = "increased" if switched else "baseline"
                else:
                    raised = (
                        vendor.key in config.tariff_increase_keys
                        and month_index >= config.increase_month_index
                    )
                    tariff = 1.0 + (vendor.tariff_increase if raised else 0.0)
                    amount = jittered(
                        draw,
                        round(vendor.base_minor * multiplier * tariff),
                        vendor.jitter,
                    )
                    if raised:
                        tier = "tariff_increase"
                    else:
                        tier = "seasonal" if multiplier != 1.0 else "stable"
                documents.append(
                    {
                        "_id": uuid7_from(draw, int(posted_at.timestamp() * 1000)),
                        "userId": user_id,
                        "rail": vendor.rail,
                        "status": "posted",
                        "sourceAccountId": accounts[user_id],
                        "targetAccountId": None,
                        "targetIban": vendor_ibans[vendor.key],
                        "counterparty": vendor.name,
                        "amountMinorUnits": amount,
                        "currency": "RON",
                        "reference": f"{vendor.reference} {month.strftime('%Y-%m')}",
                        "category": vendor.category,
                        "payeeCheck": "match",
                        "signature": None,
                        "journalTransactionId": None,
                        "rejectedReason": None,
                        "createdAt": posted_at,
                        "updatedAt": posted_at,
                        "seedBatch": config.seed_batch,
                        "seedMeta": {
                            "vendorKey": vendor.key,
                            "billingMonth": month.strftime("%Y-%m"),
                            "monthIndex": month_index,
                            "priceTier": tier,
                            "seasonalMultiplier": round(multiplier, 4),
                        },
                    }
                )

    documents.sort(key=lambda document: document["createdAt"])
    return documents, switch_month


def report(
    documents: list[dict[str, Any]],
    switch_month: dict[str, int],
    now: datetime,
    config: SeedConfig,
) -> None:
    labels = [
        month.strftime("%Y-%m") for month in month_starts(config.period_months, now)
    ]
    users = len({document["userId"] for document in documents})

    print(f"\ninserted {len(documents)} documents into '{config.collection}'")
    print(f"period : {labels[0]} .. {labels[-1]}  ({config.period_months} months)")
    print(f"users  : {users}")
    print(f"seasonal : {'on' if config.seasonal else 'off'}\n")

    if config.real_users:
        print("real users seeded with their own userId from the 'users' collection:")
        for real_user in config.real_users:
            rows = [d for d in documents if d["userId"] == real_user.user_id]
            vendors = sorted({row["seedMeta"]["vendorKey"] for row in rows})
            print(
                f"  {real_user.username:<14} userId={real_user.user_id}  "
                f"docs={len(rows):>3}  vendors={','.join(vendors)}"
            )
        print()

    header = f"{'vendor':<22}{'rail':<14}{'docs':>6}{'users':>7}{'min RON':>10}{'max RON':>10}"
    print(header)
    print("-" * len(header))
    for vendor in VENDORS:
        rows = [d for d in documents if d["seedMeta"]["vendorKey"] == vendor.key]
        if not rows:
            continue
        amounts = [row["amountMinorUnits"] for row in rows]
        print(
            f"{vendor.name:<22}{vendor.rail:<14}{len(rows):>6}"
            f"{len({row['userId'] for row in rows}):>7}"
            f"{min(amounts) / 100:>10.2f}{max(amounts) / 100:>10.2f}"
        )

    if config.seasonal:
        print("\nseasonal curve — mean / median per month (the control group must stay flat):")
        seasonal_vendors = [v for v in VENDORS if v.seasonal_amplitude > 0.0]
        flat_vendors = [v for v in VENDORS if v.seasonal_amplitude == 0.0]
        columns = seasonal_vendors + flat_vendors
        print(
            f"{'month':<9}"
            + "".join(f"{vendor.name.split()[0]:>21}" for vendor in columns)
        )
        print("-" * (9 + 21 * len(columns)))
        for label in labels:
            cells = ""
            for vendor in columns:
                rows = [
                    d["amountMinorUnits"]
                    for d in documents
                    if d["seedMeta"]["vendorKey"] == vendor.key
                    and d["seedMeta"]["billingMonth"] == label
                ]
                if not rows:
                    cells += f"{'-':>21}"
                    continue
                mean = sum(rows) / len(rows) / 100
                ordered = sorted(rows)
                middle = len(ordered) // 2
                median = (
                    ordered[middle]
                    if len(ordered) % 2
                    else (ordered[middle - 1] + ordered[middle]) / 2
                ) / 100
                cells += f"{mean:>10.2f}/{median:<10.2f}"
            print(f"{label:<9}{cells}")

    cohort_size = len(switch_month)
    print(
        f"\nNetflix price increase {NETFLIX_PRICE_BEFORE / 100:.2f} RON -> "
        f"{NETFLIX_PRICE_AFTER / 100:.2f} RON, staged across the cohort:"
    )
    cumulative = 0
    for index, label in enumerate(labels):
        switching = sum(1 for month in switch_month.values() if month == index)
        if switching == 0 and cumulative in (0, cohort_size):
            continue
        cumulative += switching
        marker = "   <-- canary wave" if index == config.increase_month_index else ""
        print(
            f"  {label}   switched this month: {switching:>2}   "
            f"on new price: {cumulative:>2}/{cohort_size}{marker}"
        )

    canary = sum(
        1 for month in switch_month.values() if month == config.increase_month_index
    )
    print(
        f"\n  first month with any increase : {labels[config.increase_month_index]} "
        f"({canary} of {cohort_size} Netflix users = {canary / cohort_size:.0%})"
    )


async def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--collection", default="payments_seed_dev")
    parser.add_argument("--batch", default="vendor-subscription-v1")
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument("--increase-month-index", type=int, default=3)
    parser.add_argument("--seasonal", action="store_true")
    parser.add_argument("--real-user", action="append", default=None)
    parser.add_argument("--vendor-increase", action="append", default=None)
    arguments = parser.parse_args()

    config = SeedConfig(
        collection=arguments.collection,
        seed_batch=arguments.batch,
        period_months=arguments.months,
        increase_month_index=arguments.increase_month_index,
        seasonal=arguments.seasonal,
        tariff_increase_keys=tuple(arguments.vendor_increase or ()),
    )
    unknown = set(config.tariff_increase_keys) - {v.key for v in VENDORS}
    if unknown:
        raise SystemExit(f"unknown vendor key(s) for --vendor-increase: {sorted(unknown)}")
    if config.increase_month_index + 2 >= config.period_months:
        raise SystemExit(
            "increase-month-index leaves no room for the three rollout waves"
        )

    uri, db_name = load_mongo_settings()
    now = datetime.now(UTC)
    started = time.perf_counter()

    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(
        uri, uuidRepresentation="standard", tz_aware=True, serverSelectionTimeoutMS=10000
    )
    try:
        db = client[db_name]
        config.real_users = await resolve_real_users(
            db, tuple(arguments.real_user or ())
        )
        validator = await clone_validator(db)
        await ensure_collection(db, validator, config)

        collection = db[config.collection]
        removed = await collection.delete_many({"seedBatch": config.seed_batch})
        documents, switch_month = build_documents(now, config)
        await collection.insert_many(documents, ordered=False)

        print(f"database   : {db_name} @ {uri}")
        print(f"seedBatch  : {config.seed_batch}")
        print(f"rail enum  : {validator['$jsonSchema']['properties']['rail']['enum']}")
        print(f"cleaned    : {removed.deleted_count} documents from a previous run")
        report(documents, switch_month, now, config)
        print(f"\ndone in {time.perf_counter() - started:.2f}s")
    finally:
        await client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
