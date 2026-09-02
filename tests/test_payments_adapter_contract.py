import asyncio
from typing import Any

from backend.vendors.detector import DetectorConfig, price_cohort_pipeline
from backend.vendors.extractor import ExtractorConfig
from backend.vendors.extractor import build_pipeline as stats_pipeline
from backend.vendors.payments_adapter import (
    AMOUNT_MINOR_UNITS,
    COUNTERPARTY,
    CREATED_AT,
    EXPECTED_FIELDS,
    RAIL,
    STATUS,
    TARGET_ACCOUNT_ID,
    assumptions_summary,
    external_payment_match,
    normalised_counterparty_expression,
    schema_warnings,
    verify_schema,
)
from backend.vendors.user_prices import UserPriceConfig
from backend.vendors.user_prices import build_pipeline as user_pipeline

HEALTHY = {
    "userId": {"bsonType": "string"},
    "targetAccountId": {"bsonType": ["string", "null"]},
    "rail": {"enum": ["internal", "sepa", "card", "direct_debit"]},
    "status": {"enum": ["draft", "pending", "posted", "rejected"]},
    "amountMinorUnits": {"bsonType": ["int", "long"], "minimum": 1},
    "counterparty": {"bsonType": "string"},
    "category": {"bsonType": "string"},
    "currency": {"enum": ["RON", "EUR"]},
    "createdAt": {"bsonType": "date"},
}


class FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        return list(self._docs)


class FakeDb:
    def __init__(self, entries: list[dict[str, Any]]) -> None:
        self._entries = entries

    async def list_collections(self, filter: dict[str, Any] | None = None) -> FakeCursor:
        name = (filter or {}).get("name")
        return FakeCursor([e for e in self._entries if e.get("name") == name])


def db_with(properties: dict[str, Any] | None) -> FakeDb:
    options: dict[str, Any] = {}
    if properties is not None:
        options = {"validator": {"$jsonSchema": {"properties": properties}}}
    return FakeDb([{"name": "payments", "options": options}])


def test_the_external_vendor_filter_is_exactly_what_it_has_always_been() -> None:
    assert external_payment_match() == {
        "status": {"$in": ["posted"]},
        "targetAccountId": None,
        "rail": {"$nin": ["internal"]},
        "amountMinorUnits": {"$gt": 0},
        "counterparty": {"$type": "string", "$ne": ""},
    }


def test_the_filter_still_honours_a_caller_that_overrides_the_defaults() -> None:
    match = external_payment_match(("posted", "pending"), ("internal", "book"))

    assert match[STATUS] == {"$in": ["posted", "pending"]}
    assert match[RAIL] == {"$nin": ["internal", "book"]}
    assert match[TARGET_ACCOUNT_ID] is None


def test_category_is_never_part_of_the_external_vendor_filter() -> None:
    assert "category" not in external_payment_match()


def test_the_counterparty_expression_reads_the_counterparty_field() -> None:
    expression = normalised_counterparty_expression()

    assert repr(expression).count(f"${COUNTERPARTY}") == 1


def test_no_pipeline_names_a_payments_field_outside_the_adapter() -> None:
    pipelines = [
        repr(stats_pipeline(ExtractorConfig(source_collection="unit"))),
        repr(user_pipeline(UserPriceConfig(source_collection="unit"))),
        repr(price_cohort_pipeline(DetectorConfig(source_collection="unit"))),
    ]

    for rendered in pipelines:
        for field in (AMOUNT_MINOR_UNITS, COUNTERPARTY, CREATED_AT):
            assert f"${field}" in rendered


def test_a_healthy_schema_raises_no_warning() -> None:
    assert schema_warnings(HEALTHY) == []


def test_a_dropped_field_is_reported_with_the_reason_we_needed_it() -> None:
    without_target = {k: v for k, v in HEALTHY.items() if k != TARGET_ACCOUNT_ID}

    warnings = schema_warnings(without_target)

    assert len(warnings) == 1
    assert TARGET_ACCOUNT_ID in warnings[0]
    assert "vendor payment" in warnings[0]


def test_a_retyped_field_is_reported() -> None:
    retyped = {**HEALTHY, AMOUNT_MINOR_UNITS: {"bsonType": "decimal"}}

    warnings = schema_warnings(retyped)

    assert len(warnings) == 1
    assert "decimal" in warnings[0]
    assert AMOUNT_MINOR_UNITS in warnings[0]


def test_a_rail_enum_that_lost_internal_breaks_our_discriminator_loudly() -> None:
    renamed = {**HEALTHY, RAIL: {"enum": ["book_transfer", "sepa", "card"]}}

    warnings = schema_warnings(renamed)

    assert len(warnings) == 1
    assert "internal" in warnings[0]


def test_a_status_enum_that_lost_posted_is_reported() -> None:
    renamed = {**HEALTHY, STATUS: {"enum": ["draft", "settled", "rejected"]}}

    warnings = schema_warnings(renamed)

    assert len(warnings) == 1
    assert "posted" in warnings[0]


def test_several_changes_are_all_reported_not_just_the_first() -> None:
    broken = {k: v for k, v in HEALTHY.items() if k not in (COUNTERPARTY, CREATED_AT)}
    broken[RAIL] = {"enum": ["sepa"]}

    warnings = schema_warnings(broken)

    assert len(warnings) == 3


def test_a_collection_without_a_validator_is_flagged_not_assumed_healthy() -> None:
    warnings = asyncio.run(verify_schema(db_with(None), "payments"))

    assert len(warnings) == 1
    assert "no $jsonSchema validator" in warnings[0]


def test_a_missing_collection_is_flagged() -> None:
    warnings = asyncio.run(verify_schema(FakeDb([]), "payments"))

    assert len(warnings) == 1
    assert "does not exist" in warnings[0]


def test_the_guard_passes_against_a_healthy_collection() -> None:
    assert asyncio.run(verify_schema(db_with(HEALTHY), "payments")) == []


def test_the_shareable_summary_lists_every_field_the_pipeline_reads() -> None:
    summary = assumptions_summary()

    for field in EXPECTED_FIELDS:
        assert field.name in summary
        assert field.why in summary
    assert "Doar citire" in summary
