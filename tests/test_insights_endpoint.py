from datetime import UTC, datetime
from typing import Any

import pytest

from backend.config import settings
from backend.vendors.service import (
    VendorInsightsService,
    newest_per_vendor,
    one_per_vendor_month,
    to_insight,
)

SOURCE = "payments_seed_demo"
GABRIELA = "01a01ed4-99bc-728d-8a58-a239b290a161"
MARIA = "01a01ed4-99bc-728d-8a58-a239b290a162"


def notification(
    vendor: str,
    month: str,
    user_id: str = GABRIELA,
    identifier: str = "id",
) -> dict[str, Any]:
    return {
        "_id": identifier,
        "source": SOURCE,
        "userId": user_id,
        "vendorNormalized": vendor,
        "vendorDisplayName": vendor.title(),
        "vendorCategory": "entertainment",
        "currency": "RON",
        "month": month,
        "alertType": "predictive",
        "confidence": "high",
        "origin": "external_news_predictive",
        "percentChange": 0.20,
        "vendorPercentChange": 0.20,
        "baselineMinorUnits": 4900,
        "observedMinorUnits": 5900,
        "shortText": f"{vendor} +20%",
        "longText": "Ultima ta plată a fost de {baseline}.",
        "shortTextEn": f"{vendor} +20%",
        "longTextEn": "Your last payment was {baseline}.",
        "newsEventKey": "event-1",
        "newsPublishers": ["The Guardian"],
        "newsUrls": ["https://news.example/1"],
        "newsEffectiveDate": None,
        "newsMarket": None,
        "status": "pending",
        "createdAt": datetime(2026, 8, 26, 12, 0, 0, tzinfo=UTC),
    }


class FakeCursor:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = items

    def sort(self, *args: Any, **kwargs: Any) -> "FakeCursor":
        return self

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        return self.items


class FakeCollection:
    def __init__(self, documents: list[dict[str, Any]], recorder: dict[str, Any]) -> None:
        self.documents = documents
        self.recorder = recorder

    def find(self, query: dict[str, Any]) -> FakeCursor:
        self.recorder["query"] = query
        matched = [
            row
            for row in self.documents
            if all(row.get(field) == value for field, value in query.items())
        ]
        return FakeCursor(matched)


class FakeDB:
    def __init__(self, documents: list[dict[str, Any]], recorder: dict[str, Any]) -> None:
        self.documents = documents
        self.recorder = recorder

    def __getitem__(self, name: str) -> FakeCollection:
        return FakeCollection(self.documents, self.recorder)


def service_over(
    monkeypatch: pytest.MonkeyPatch,
    documents: list[dict[str, Any]],
    limit: int = 3,
) -> tuple[VendorInsightsService, dict[str, Any]]:
    recorder: dict[str, Any] = {}
    monkeypatch.setattr(
        "backend.vendors.service.get_db", lambda: FakeDB(documents, recorder)
    )
    config = settings.model_copy(
        update={"vendor_insights_source": SOURCE, "vendor_insights_limit": limit}
    )
    return VendorInsightsService(config=config), recorder


@pytest.mark.anyio
async def test_a_user_without_notifications_is_never_shown_another_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = [notification("NETFLIX", "2026-08", identifier="a")]
    service, _ = service_over(monkeypatch, documents)

    mine = await service.list_for_user(GABRIELA)
    theirs = await service.list_for_user(MARIA)

    assert [row.vendorNormalized for row in mine] == ["NETFLIX"]
    assert theirs == []


@pytest.mark.anyio
async def test_the_query_is_always_scoped_to_the_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = [notification("NETFLIX", "2026-08", identifier="a")]
    service, recorder = service_over(monkeypatch, documents)

    await service.list_for_user(GABRIELA)

    assert recorder["query"]["userId"] == GABRIELA
    assert recorder["query"]["source"] == SOURCE


@pytest.mark.anyio
async def test_one_row_per_vendor_survives_the_dedupe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = [
        notification("NETFLIX", "2026-08", identifier="newest"),
        notification("NETFLIX", "2026-07", identifier="older"),
        notification("DIGI COMMUNICATIONS", "2026-07", identifier="digi"),
    ]
    service, _ = service_over(monkeypatch, documents)

    rows = await service.list_for_user(GABRIELA)

    assert [row.vendorNormalized for row in rows] == ["NETFLIX", "DIGI COMMUNICATIONS"]
    assert rows[0].id == "newest"


@pytest.mark.anyio
async def test_the_configured_limit_caps_the_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = [
        notification("NETFLIX", "2026-08", identifier="a"),
        notification("DIGI COMMUNICATIONS", "2026-08", identifier="b"),
        notification("ENEL ENERGIE", "2026-08", identifier="c"),
        notification("OMV PETROM", "2026-08", identifier="d"),
    ]
    service, _ = service_over(monkeypatch, documents, limit=2)

    rows = await service.list_for_user(GABRIELA)

    assert len(rows) == 2


def test_the_dedupe_keeps_the_first_row_of_each_vendor() -> None:
    rows = [
        {"vendorNormalized": "NETFLIX", "_id": "first"},
        {"vendorNormalized": "NETFLIX", "_id": "second"},
        {"vendorNormalized": "DIGI", "_id": "third"},
        {"vendorNormalized": None, "_id": "skipped"},
    ]

    kept = newest_per_vendor(rows, 5)

    assert [row["_id"] for row in kept] == ["first", "third"]


def test_the_wire_shape_carries_money_as_numbers_not_text() -> None:
    insight = to_insight(notification("NETFLIX", "2026-08", identifier="a"))

    assert insight.baselineMinorUnits == 4900
    assert insight.observedMinorUnits == 5900
    assert insight.currency == "RON"
    assert "{baseline}" in (insight.longText or "")
    assert insight.createdAt == "2026-08-26T12:00:00+00:00"


@pytest.mark.anyio
async def test_the_card_is_capped_but_the_history_keeps_every_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = [
        notification("NETFLIX", "2026-08", identifier="n1"),
        notification("NETFLIX", "2026-07", identifier="n2"),
        notification("ENEL ENERGIE", "2026-07", identifier="e1"),
        notification("ENEL ENERGIE", "2026-06", identifier="e2"),
        notification("DIGI COMMUNICATIONS", "2026-07", identifier="d1"),
    ]
    service, _ = service_over(monkeypatch, documents, limit=3)

    board = await service.board_for_user(GABRIELA)

    assert [row.vendorNormalized for row in board.insights] == [
        "NETFLIX",
        "ENEL ENERGIE",
        "DIGI COMMUNICATIONS",
    ]
    assert len(board.history) == 5
    assert board.total == 5


@pytest.mark.anyio
async def test_a_user_without_alerts_has_an_empty_history_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = [notification("NETFLIX", "2026-08", identifier="n1")]
    service, _ = service_over(monkeypatch, documents)

    board = await service.board_for_user(MARIA)

    assert board.insights == []
    assert board.history == []
    assert board.total == 0


def test_one_price_rise_is_listed_once_even_when_two_mechanisms_saw_it() -> None:
    rows = [
        {"vendorNormalized": "ENEL", "month": "2026-07", "alertType": "predictive", "_id": "p"},
        {"vendorNormalized": "ENEL", "month": "2026-07", "alertType": "confirmed", "_id": "c"},
        {"vendorNormalized": "ENEL", "month": "2026-06", "alertType": "predictive", "_id": "june"},
    ]

    kept = one_per_vendor_month(rows)

    assert [row["_id"] for row in kept] == ["c", "june"]
