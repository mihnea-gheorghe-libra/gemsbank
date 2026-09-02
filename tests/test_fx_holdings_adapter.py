from typing import Any

from backend.fx.adapters import (
    ACCOUNTS_COLLECTION,
    EXPECTED_ACCOUNT_FIELDS,
    EXPECTED_JOURNAL_FIELDS,
    JOURNAL_COLLECTION,
    assumptions_summary,
    balance_pipeline,
    currency_holdings,
    fold_holdings,
    held_foreign_currencies,
    holding_match,
    json_schema_of,
    missing_collections,
    schema_warnings,
    verify_schema,
)

GABRIELA = "01a01ed4-99bc-728d-8a58-a239b290a161"
MARIA = "01a01f08-343e-79d8-b22e-a30d1ad2e358"

ACCOUNTS = [
    {"_id": "a-eur-1", "userId": GABRIELA, "currency": "EUR", "status": "active"},
    {"_id": "a-eur-2", "userId": GABRIELA, "currency": "EUR", "status": "active"},
    {"_id": "a-usd-1", "userId": GABRIELA, "currency": "USD", "status": "active"},
    {"_id": "m-eur-1", "userId": MARIA, "currency": "EUR", "status": "active"},
    {"_id": "m-eur-2", "userId": MARIA, "currency": "EUR", "status": "closed"},
    {"_id": "r-ron-1", "userId": GABRIELA, "currency": "RON", "status": "active"},
]

JOURNAL = [
    {"entries": [{"accountId": "a-eur-1", "amount": 10000}, {"accountId": "h", "amount": -10000}]},
    {"entries": [{"accountId": "a-eur-2", "amount": 5000}, {"accountId": "h", "amount": -5000}]},
    {"entries": [{"accountId": "a-eur-1", "amount": -2000}, {"accountId": "h", "amount": 2000}]},
    {"entries": [{"accountId": "m-eur-2", "amount": 99999}, {"accountId": "h", "amount": -99999}]},
    {"entries": [{"accountId": "r-ron-1", "amount": 250000}, {"accountId": "h", "amount": -250000}]},
]


class FakeCursor:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = items

    def sort(self, *args: Any, **kwargs: Any) -> "FakeCursor":
        return self

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        return self.items


class FakeCollection:
    def __init__(self, name: str, recorder: dict[str, Any]) -> None:
        self.name = name
        self.recorder = recorder

    def find(
        self, query: dict[str, Any], projection: dict[str, Any] | None = None
    ) -> FakeCursor:
        self.recorder.setdefault("finds", []).append((self.name, query))
        return FakeCursor(
            [
                row
                for row in ACCOUNTS
                if row["currency"] in query["currency"]["$in"]
                and row["status"] in query["status"]["$in"]
            ]
        )

    async def aggregate(self, pipeline: list[dict[str, Any]]) -> FakeCursor:
        self.recorder["pipeline"] = pipeline
        wanted = set(pipeline[0]["$match"]["entries.accountId"]["$in"])
        totals: dict[str, int] = {}
        for transaction in JOURNAL:
            for entry in transaction["entries"]:
                if entry["accountId"] in wanted:
                    totals[entry["accountId"]] = (
                        totals.get(entry["accountId"], 0) + entry["amount"]
                    )
        return FakeCursor([{"_id": key, "total": value} for key, value in totals.items()])

    async def distinct(self, field: str, query: dict[str, Any]) -> list[Any]:
        self.recorder["distinct"] = (field, query)
        return sorted(
            {
                row["currency"]
                for row in ACCOUNTS
                if row["currency"] != "RON" and row["status"] in query["status"]["$in"]
            }
        )


class FakeDB:
    def __init__(self, recorder: dict[str, Any]) -> None:
        self.recorder = recorder

    def __getitem__(self, name: str) -> FakeCollection:
        return FakeCollection(name, self.recorder)


def test_the_filter_only_ever_asks_for_active_accounts_in_tracked_currencies() -> None:
    query = holding_match(("eur", "USD"))

    assert query["currency"]["$in"] == ["EUR", "USD"]
    assert query["status"]["$in"] == ["active"]


def test_a_balance_is_derived_from_journal_lines_and_never_read_from_a_field() -> None:
    pipeline = balance_pipeline(["a-eur-1"])

    assert [stage for stage in pipeline if "$unwind" in stage]
    assert pipeline[-1]["$group"]["total"] == {"$sum": "$entries.amount"}
    assert not any("balance" in str(stage).lower() for stage in pipeline)


def test_two_accounts_in_the_same_currency_fold_into_one_holding() -> None:
    balances = {"a-eur-1": 8000, "a-eur-2": 5000}

    holdings = fold_holdings(
        [row for row in ACCOUNTS if row["_id"] in balances], balances
    )

    assert len(holdings) == 1
    assert holdings[0]["userId"] == GABRIELA
    assert holdings[0]["amountMinorUnits"] == 13000
    assert holdings[0]["accountIds"] == ["a-eur-1", "a-eur-2"]


def test_an_account_with_no_journal_line_folds_in_as_zero_not_as_missing() -> None:
    holdings = fold_holdings([ACCOUNTS[2]], {})

    assert holdings[0]["currency"] == "USD"
    assert holdings[0]["amountMinorUnits"] == 0


async def test_a_closed_account_is_not_a_holding_however_much_it_holds() -> None:
    recorder: dict[str, Any] = {}

    holdings = await currency_holdings(FakeDB(recorder), ("EUR", "USD"))

    by_user = {(row["userId"], row["currency"]): row for row in holdings}
    assert by_user[(GABRIELA, "EUR")]["amountMinorUnits"] == 13000
    assert by_user[(GABRIELA, "USD")]["amountMinorUnits"] == 0
    assert by_user[(MARIA, "EUR")]["amountMinorUnits"] == 0
    assert "m-eur-2" not in str(holdings)


async def test_ron_accounts_are_never_pulled_in_as_a_foreign_holding() -> None:
    holdings = await currency_holdings(FakeDB({}), ("EUR", "USD"))

    assert all(row["currency"] != "RON" for row in holdings)


async def test_the_tracked_currencies_can_be_read_off_the_real_accounts() -> None:
    held = await held_foreign_currencies(FakeDB({}))

    assert held == ("EUR", "USD")


async def test_no_tracked_currency_means_no_query_at_all() -> None:
    recorder: dict[str, Any] = {}

    assert await currency_holdings(FakeDB(recorder), ()) == []
    assert "finds" not in recorder


def test_the_schema_guard_notices_a_field_that_disappeared() -> None:
    warnings = schema_warnings({"userId": {"bsonType": "string"}}, EXPECTED_ACCOUNT_FIELDS)

    assert any("currency" in warning for warning in warnings)
    assert any("status" in warning for warning in warnings)


def test_the_schema_guard_notices_a_currency_enum_that_dropped_ron() -> None:
    properties = {
        "userId": {"bsonType": "string"},
        "currency": {"bsonType": "string", "enum": ["EUR", "USD"]},
        "status": {"bsonType": "string", "enum": ["active", "frozen", "closed"]},
        "kind": {"bsonType": "string"},
    }

    warnings = schema_warnings(properties, EXPECTED_ACCOUNT_FIELDS)

    assert len(warnings) == 1
    assert "RON" in warnings[0]


def test_a_schema_that_still_matches_raises_nothing() -> None:
    properties = {
        "userId": {"bsonType": "string"},
        "currency": {"enum": ["RON", "EUR", "USD"]},
        "status": {"enum": ["active", "frozen", "closed"]},
        "kind": {"enum": ["current", "savings", "invest"]},
    }

    assert schema_warnings(properties, EXPECTED_ACCOUNT_FIELDS) == []


def test_the_journal_validator_is_found_inside_its_and_clause() -> None:
    validator = {
        "$and": [
            {"$jsonSchema": {"properties": {"entries": {"bsonType": "array"}}}},
            {"$expr": {"$eq": [{"$sum": "$entries.amount"}, 0]}},
        ]
    }

    schema = json_schema_of(validator)

    assert schema is not None
    assert "entries" in schema["properties"]


class NoCollectionsDB:
    async def list_collections(self, filter: dict[str, Any]) -> FakeCursor:
        return FakeCursor([])


async def test_a_source_collection_that_is_gone_stops_the_job_instead_of_returning_zero() -> None:
    warnings = await verify_schema(
        NoCollectionsDB(), ACCOUNTS_COLLECTION, EXPECTED_ACCOUNT_FIELDS
    )

    assert missing_collections({ACCOUNTS_COLLECTION: warnings}) == [ACCOUNTS_COLLECTION]


def test_the_account_assumptions_are_written_down_somewhere_a_human_can_read() -> None:
    summary = assumptions_summary()

    assert ACCOUNTS_COLLECTION in summary
    assert JOURNAL_COLLECTION in summary
    for field in EXPECTED_ACCOUNT_FIELDS + EXPECTED_JOURNAL_FIELDS:
        assert field.name in summary
        assert field.why in summary
