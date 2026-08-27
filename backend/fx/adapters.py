from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from backend.fx.validation import BASE_CURRENCY

ACCOUNTS_COLLECTION = "accounts"
JOURNAL_COLLECTION = "journalTransactions"

ACCOUNT_ID = "_id"
USER_ID = "userId"
CURRENCY = "currency"
STATUS = "status"
KIND = "kind"

ENTRIES = "entries"
ENTRY_ACCOUNT_ID = "entries.accountId"
ENTRY_AMOUNT = "entries.amount"

DEFAULT_HOLDING_STATUSES = ("active",)


class SourceField(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    bson_types: tuple[str, ...] = ()
    enum_must_contain: tuple[str, ...] = ()
    why: str


EXPECTED_ACCOUNT_FIELDS: tuple[SourceField, ...] = (
    SourceField(
        name=USER_ID,
        bson_types=("string",),
        why="identifies the holder an FX insight is written for",
    ),
    SourceField(
        name=CURRENCY,
        bson_types=("string",),
        enum_must_contain=(BASE_CURRENCY,),
        why="ISO 4217 code; a non-RON account is what exposes a holder to the rate",
    ),
    SourceField(
        name=STATUS,
        bson_types=("string",),
        enum_must_contain=DEFAULT_HOLDING_STATUSES,
        why="only an active account is a holding a customer can act on",
    ),
    SourceField(
        name=KIND,
        bson_types=("string",),
        why="reported only; current, savings and invest all count as a holding",
    ),
)

EXPECTED_JOURNAL_FIELDS: tuple[SourceField, ...] = (
    SourceField(
        name=ENTRIES,
        bson_types=("array",),
        why="balances are derived from journal lines; there is no balance field to read",
    ),
    SourceField(
        name=CURRENCY,
        bson_types=("string",),
        why="reported only; the account currency decides which rate applies",
    ),
)


def holding_match(
    currencies: tuple[str, ...],
    statuses: tuple[str, ...] = DEFAULT_HOLDING_STATUSES,
) -> dict[str, Any]:
    return {
        CURRENCY: {"$in": sorted({value.upper() for value in currencies})},
        STATUS: {"$in": list(statuses)},
    }


def foreign_account_match(
    statuses: tuple[str, ...] = DEFAULT_HOLDING_STATUSES,
) -> dict[str, Any]:
    return {CURRENCY: {"$ne": BASE_CURRENCY}, STATUS: {"$in": list(statuses)}}


def balance_pipeline(account_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {"$match": {ENTRY_ACCOUNT_ID: {"$in": account_ids}}},
        {"$unwind": f"${ENTRIES}"},
        {"$match": {ENTRY_ACCOUNT_ID: {"$in": account_ids}}},
        {
            "$group": {
                "_id": f"${ENTRY_ACCOUNT_ID}",
                "total": {"$sum": f"${ENTRY_AMOUNT}"},
            }
        },
    ]


def fold_holdings(
    accounts: list[dict[str, Any]], balances: dict[str, int]
) -> list[dict[str, Any]]:
    totals: dict[tuple[str, str], dict[str, Any]] = {}
    for account in accounts:
        user_id = account.get(USER_ID)
        currency = account.get(CURRENCY)
        account_id = account.get(ACCOUNT_ID)
        if not isinstance(user_id, str) or not isinstance(currency, str):
            continue
        if not isinstance(account_id, str):
            continue
        key = (user_id, currency.upper())
        holding = totals.setdefault(
            key,
            {
                "userId": user_id,
                "currency": currency.upper(),
                "amountMinorUnits": 0,
                "accountIds": [],
            },
        )
        holding["amountMinorUnits"] += int(balances.get(account_id, 0))
        holding["accountIds"].append(account_id)
    for holding in totals.values():
        holding["accountIds"].sort()
    return [totals[key] for key in sorted(totals)]


async def read_balances(db: Any, account_ids: list[str]) -> dict[str, int]:
    if not account_ids:
        return {}
    cursor = await db[JOURNAL_COLLECTION].aggregate(balance_pipeline(account_ids))
    found = await cursor.to_list(length=None)
    return {str(row["_id"]): int(row["total"]) for row in found}


async def currency_holdings(
    db: Any,
    currencies: tuple[str, ...],
    statuses: tuple[str, ...] = DEFAULT_HOLDING_STATUSES,
) -> list[dict[str, Any]]:
    if not currencies:
        return []
    accounts = (
        await db[ACCOUNTS_COLLECTION]
        .find(
            holding_match(currencies, statuses),
            {ACCOUNT_ID: 1, USER_ID: 1, CURRENCY: 1},
        )
        .to_list(length=None)
    )
    balances = await read_balances(db, [str(row[ACCOUNT_ID]) for row in accounts])
    return fold_holdings(accounts, balances)


async def held_foreign_currencies(
    db: Any, statuses: tuple[str, ...] = DEFAULT_HOLDING_STATUSES
) -> tuple[str, ...]:
    found = await db[ACCOUNTS_COLLECTION].distinct(
        CURRENCY, foreign_account_match(statuses)
    )
    return tuple(
        sorted(
            {
                value.strip().upper()
                for value in found
                if isinstance(value, str) and value.strip()
            }
        )
    )


def json_schema_of(validator: dict[str, Any]) -> dict[str, Any] | None:
    direct = validator.get("$jsonSchema")
    if isinstance(direct, dict):
        return direct
    for clause in validator.get("$and") or []:
        if not isinstance(clause, dict):
            continue
        nested = clause.get("$jsonSchema")
        if isinstance(nested, dict):
            return nested
    return None


async def read_validator_properties(
    db: Any, collection: str
) -> tuple[dict[str, Any] | None, str | None]:
    cursor = await db.list_collections(filter={"name": collection})
    entries = await cursor.to_list(length=1)
    if not entries:
        return None, f"collection {collection} does not exist"
    options = entries[0].get("options") or {}
    schema = json_schema_of(options.get("validator") or {})
    properties = (schema or {}).get("properties")
    if not properties:
        return None, f"collection {collection} has no jsonSchema validator to check"
    return properties, None


def schema_warnings(
    properties: dict[str, Any], expected: tuple[SourceField, ...]
) -> list[str]:
    warnings: list[str] = []
    for field in expected:
        declared = properties.get(field.name)
        if declared is None:
            warnings.append(f"field {field.name} is gone from the schema — {field.why}")
            continue

        raw_type = declared.get("bsonType")
        declared_types = (
            tuple(raw_type)
            if isinstance(raw_type, list)
            else ((raw_type,) if isinstance(raw_type, str) else ())
        )
        if field.bson_types and declared_types and not (
            set(field.bson_types) & set(declared_types)
        ):
            warnings.append(
                f"field {field.name} is now {list(declared_types)}, "
                f"we read it as {list(field.bson_types)}"
            )

        if field.enum_must_contain:
            declared_enum = declared.get("enum")
            if isinstance(declared_enum, list):
                missing = [
                    value
                    for value in field.enum_must_contain
                    if value not in declared_enum
                ]
                if missing:
                    warnings.append(
                        f"field {field.name} no longer allows {missing} — {field.why}"
                    )
    return warnings


async def verify_schema(
    db: Any, collection: str, expected: tuple[SourceField, ...]
) -> list[str]:
    properties, problem = await read_validator_properties(db, collection)
    if problem is not None:
        return [problem]
    assert properties is not None
    return schema_warnings(properties, expected)


def render_warnings(collection: str, warnings: list[str]) -> str:
    if not warnings:
        return ""
    lines = [
        "",
        "=" * 78,
        f"ATENTIE: schema {collection} s-a schimbat fata de ce presupune backend/fx/.",
        "Verifica backend/fx/adapters.py inainte sa ai incredere in rezultate.",
        "=" * 78,
    ]
    lines += [f"  - {warning}" for warning in warnings]
    lines.append("=" * 78)
    lines.append("")
    return "\n".join(lines)


async def warn_if_schema_changed(db: Any) -> dict[str, list[str]]:
    reported: dict[str, list[str]] = {}
    for collection, expected in (
        (ACCOUNTS_COLLECTION, EXPECTED_ACCOUNT_FIELDS),
        (JOURNAL_COLLECTION, EXPECTED_JOURNAL_FIELDS),
    ):
        warnings = await verify_schema(db, collection, expected)
        reported[collection] = warnings
        rendered = render_warnings(collection, warnings)
        if rendered:
            print(rendered)
    return reported


def missing_collections(reported: dict[str, list[str]]) -> list[str]:
    return [
        collection
        for collection, warnings in reported.items()
        if any(warning.endswith("does not exist") for warning in warnings)
    ]


def assumptions_summary() -> str:
    lines = [
        "Ce citeste backend/fx/ din `accounts` si `journalTransactions`",
        "=" * 62,
        "",
        "Doar citire. Nu scriem niciodata in niciuna dintre ele.",
        "",
        "Nu exista un adaptor de conturi echivalent cu cel de payments:",
        "backend/accounts/service.py este legat de aplicatie prin DI si nu poate fi",
        "apelat dintr-un job standalone. Presupunerile de mai jos sunt ale noastre si",
        "traiesc doar in acest fisier.",
        "",
        "Filtrul care selecteaza un cont expus la curs:",
        f"  {CURRENCY} in valutele urmarite (deci != {BASE_CURRENCY})",
        f"  {STATUS} in {list(DEFAULT_HOLDING_STATUSES)}",
        "",
        "Soldul NU se citeste dintr-un camp. Se deriva din liniile de jurnal, exact ca",
        f"in ledger: suma lui {ENTRY_AMOUNT} peste toate documentele din",
        f"`{JOURNAL_COLLECTION}` care au o intrare cu {ENTRY_ACCOUNT_ID} egal cu _id-ul",
        "contului. Conturile aceluiasi user in aceeasi valuta se aduna intr-o singura",
        "detinere.",
        "",
        "Campurile citite si de ce:",
    ]
    for field in EXPECTED_ACCOUNT_FIELDS:
        lines.append(f"  {ACCOUNTS_COLLECTION}.{field.name:<12} {field.why}")
    for field in EXPECTED_JOURNAL_FIELDS:
        lines.append(f"  {JOURNAL_COLLECTION}.{field.name:<12} {field.why}")
    lines += [
        "",
        "Daca schimbi vreunul dintre ele, pipeline-ul FX se opreste la",
        "backend/fx/adapters.py si nicaieri altundeva.",
    ]
    return "\n".join(lines)


def main() -> int:
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(assumptions_summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
