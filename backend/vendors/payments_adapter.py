"""Every assumption backend/vendors/ makes about the `payments` collection lives here.

`payments` belongs to the Payments & Cards track. Nothing else under backend/vendors/
may name one of its fields or rebuild its filter; they compose the helpers below. When
that schema changes, this file is the one that breaks, and the schema guard says so out
loud instead of letting a pipeline quietly return nothing.

Why each field is read the way it is:

targetAccountId  The discriminator for "external vendor payment", and the only one that
                 is structural. Payments.service asserts it is set before posting, and a
                 payment can only reach an account held at GEMS, so a posted payment with
                 targetAccountId set IS an internal P2P transfer, guaranteed by code and
                 not by user input. null therefore means the money left for a vendor.

rail             System-assigned and enum-constrained by the DB validator, never typed by
                 a customer. Used as the secondary check. We exclude the internal rails
                 rather than whitelisting external ones, so a new external rail is picked
                 up automatically instead of disappearing.

status           Only settled money counts. draft, pending, awaiting_signature and
                 rejected payments must never reach a price statistic; a rejected 500 RON
                 payment would otherwise poison a vendor's max and median.

category         NOT a discriminator. It is chosen by the customer from a whitelist, and
                 on real data 6 of 13 P2P transfers carry utilities/entertainment/
                 transport/groceries rather than transfer. Filtering P2P on
                 category == "transfer" misses about 46% of it. Read for reporting only.

counterparty     Free text typed by the customer, so it is folded (diacritics, case,
                 whitespace) before it can serve as a vendor identity. Never trusted raw.

amountMinorUnits Integer minor units. Required positive; the money core forbids floats.

currency         ISO 4217. Part of every grouping key: mixing RON and EUR into one median
                 would be meaningless.

createdAt        The event time a payment is bucketed by, in Europe/Bucharest, so a
                 monthly bucket matches the customer's billing month.

userId           Identity of the payer, for per-user price history and cohort counts.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

PAYMENTS_COLLECTION = "payments"

USER_ID = "userId"
TARGET_ACCOUNT_ID = "targetAccountId"
RAIL = "rail"
STATUS = "status"
AMOUNT_MINOR_UNITS = "amountMinorUnits"
COUNTERPARTY = "counterparty"
CATEGORY = "category"
CURRENCY = "currency"
CREATED_AT = "createdAt"

DEFAULT_SETTLED_STATUSES = ("posted",)
DEFAULT_INTERNAL_RAILS = ("internal",)

DIACRITIC_FOLDING = (
    ("ă", "a"),
    ("Ă", "A"),
    ("â", "a"),
    ("Â", "A"),
    ("î", "i"),
    ("Î", "I"),
    ("ș", "s"),
    ("Ș", "S"),
    ("ş", "s"),
    ("Ş", "S"),
    ("ț", "t"),
    ("Ț", "T"),
    ("ţ", "t"),
    ("Ţ", "T"),
)

WHITESPACE_FOLDING = (("\t", " "), ("\n", " "), ("\r", " "), (" ", " "))


class SourceField(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    bson_types: tuple[str, ...]
    enum_must_contain: tuple[str, ...] = ()
    why: str


EXPECTED_FIELDS: tuple[SourceField, ...] = (
    SourceField(
        name=USER_ID,
        bson_types=("string",),
        why="identifies the payer, for per-user price history and cohort counts",
    ),
    SourceField(
        name=TARGET_ACCOUNT_ID,
        bson_types=("string", "null"),
        why="null means the money left GEMS, which is how we recognise a vendor payment",
    ),
    SourceField(
        name=RAIL,
        bson_types=("string",),
        enum_must_contain=DEFAULT_INTERNAL_RAILS,
        why="system-assigned; we exclude the internal rails to isolate external payments",
    ),
    SourceField(
        name=STATUS,
        bson_types=("string",),
        enum_must_contain=DEFAULT_SETTLED_STATUSES,
        why="only settled money counts towards a price statistic",
    ),
    SourceField(
        name=AMOUNT_MINOR_UNITS,
        bson_types=("int", "long"),
        why="the price itself, in integer minor units",
    ),
    SourceField(
        name=COUNTERPARTY,
        bson_types=("string",),
        why="free text typed by the customer; folded before it can identify a vendor",
    ),
    SourceField(
        name=CATEGORY,
        bson_types=("string",),
        why="customer-chosen label, reported but never used to tell P2P from a vendor",
    ),
    SourceField(
        name=CURRENCY,
        bson_types=("string",),
        why="ISO 4217 code, part of every grouping key so currencies never mix",
    ),
    SourceField(
        name=CREATED_AT,
        bson_types=("date",),
        why="event time a payment is bucketed by, in the customer's local month",
    ),
)


def ref(field: str) -> str:
    return f"${field}"


def external_payment_match(
    settled_statuses: tuple[str, ...] = DEFAULT_SETTLED_STATUSES,
    internal_rails: tuple[str, ...] = DEFAULT_INTERNAL_RAILS,
) -> dict[str, Any]:
    return {
        STATUS: {"$in": list(settled_statuses)},
        TARGET_ACCOUNT_ID: None,
        RAIL: {"$nin": list(internal_rails)},
        AMOUNT_MINOR_UNITS: {"$gt": 0},
        COUNTERPARTY: {"$type": "string", "$ne": ""},
    }


def normalised_counterparty_expression() -> dict[str, Any]:
    folded: Any = {"$ifNull": [ref(COUNTERPARTY), ""]}
    for source, replacement in DIACRITIC_FOLDING + WHITESPACE_FOLDING:
        folded = {
            "$replaceAll": {
                "input": folded,
                "find": source,
                "replacement": replacement,
            }
        }
    words = {
        "$filter": {
            "input": {"$split": [{"$toUpper": folded}, " "]},
            "cond": {"$ne": ["$$this", ""]},
        }
    }
    return {
        "$trim": {
            "input": {
                "$reduce": {
                    "input": words,
                    "initialValue": "",
                    "in": {"$concat": ["$$value", " ", "$$this"]},
                }
            }
        }
    }


def month_label_expression(timezone: str) -> dict[str, Any]:
    return {
        "$dateToString": {
            "date": ref(CREATED_AT),
            "format": "%Y-%m",
            "timezone": timezone,
        }
    }


def month_start_expression(timezone: str) -> dict[str, Any]:
    return {
        "$dateTrunc": {
            "date": ref(CREATED_AT),
            "unit": "month",
            "timezone": timezone,
        }
    }


async def read_validator_properties(
    db: Any, collection: str
) -> tuple[dict[str, Any] | None, str | None]:
    cursor = await db.list_collections(filter={"name": collection})
    entries = await cursor.to_list(length=1)
    if not entries:
        return None, f"collection '{collection}' does not exist"
    options = entries[0].get("options") or {}
    validator = options.get("validator") or {}
    schema = validator.get("$jsonSchema") or {}
    properties = schema.get("properties")
    if not properties:
        return None, f"collection '{collection}' has no $jsonSchema validator to check"
    return properties, None


def schema_warnings(properties: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for field in EXPECTED_FIELDS:
        declared = properties.get(field.name)
        if declared is None:
            warnings.append(
                f"field '{field.name}' is gone from the schema — {field.why}"
            )
            continue

        raw_type = declared.get("bsonType")
        declared_types = (
            tuple(raw_type)
            if isinstance(raw_type, list)
            else ((raw_type,) if isinstance(raw_type, str) else ())
        )
        if declared_types and not set(field.bson_types) & set(declared_types):
            warnings.append(
                f"field '{field.name}' is now {list(declared_types)}, "
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
                        f"field '{field.name}' no longer allows {missing} — "
                        f"{field.why}"
                    )
    return warnings


async def verify_schema(db: Any, collection: str) -> list[str]:
    properties, problem = await read_validator_properties(db, collection)
    if problem is not None:
        return [problem]
    assert properties is not None
    return schema_warnings(properties)


def render_warnings(collection: str, warnings: list[str]) -> str:
    if not warnings:
        return ""
    lines = [
        "",
        "=" * 78,
        f"ATENTIE: schema '{collection}' s-a schimbat fata de ce presupune "
        "backend/vendors/.",
        "Verifica backend/vendors/payments_adapter.py inainte sa ai incredere "
        "in rezultate.",
        "=" * 78,
    ]
    lines += [f"  - {warning}" for warning in warnings]
    lines.append("=" * 78)
    lines.append("")
    return "\n".join(lines)


async def warn_if_schema_changed(db: Any, collection: str) -> list[str]:
    warnings = await verify_schema(db, collection)
    rendered = render_warnings(collection, warnings)
    if rendered:
        print(rendered)
    return warnings


def assumptions_summary() -> str:
    lines = [
        "Ce citeste backend/vendors/ din colectia `payments`",
        "=" * 52,
        "",
        "Doar citire. Nu scriem niciodata in `payments`.",
        "",
        "Filtrul care selecteaza o plata catre vendor extern:",
        f"  {STATUS} in {list(DEFAULT_SETTLED_STATUSES)}",
        f"  {TARGET_ACCOUNT_ID} == null",
        f"  {RAIL} not in {list(DEFAULT_INTERNAL_RAILS)}",
        f"  {AMOUNT_MINOR_UNITS} > 0",
        f"  {COUNTERPARTY} este string nevid",
        "",
        "Campurile citite si de ce:",
    ]
    for field in EXPECTED_FIELDS:
        lines.append(f"  {field.name:<18} {field.why}")
    lines += [
        "",
        "Daca schimbi vreunul dintre ele, spune-ne: pipeline-ul de vendori se",
        "opreste la backend/vendors/payments_adapter.py si nicaieri altundeva.",
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
