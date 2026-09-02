from datetime import UTC, datetime
from typing import Any

import pytest

from backend.config import settings
from backend.fx.service import (
    FxInsightsService,
    newest_per_currency,
    one_per_currency_signal,
    to_insight,
)

SOURCE = "bnr"
GABRIELA = "01a01ed4-99bc-728d-8a58-a239b290a161"
MARIA = "01a01ed4-99bc-728d-8a58-a239b290a162"


def notification(
    currency: str,
    signal_date: str,
    user_id: str = GABRIELA,
    identifier: str = "id",
) -> dict[str, Any]:
    return {
        "_id": identifier,
        "source": SOURCE,
        "userId": user_id,
        "currency": currency,
        "signalDate": signal_date,
        "signalKey": f"{SOURCE}:{currency}:{signal_date}",
        "direction": "up",
        "changePercent": 1.5232,
        "baselineRate": 5_180_000,
        "currentRate": 5_258_900,
        "baselineDate": "2026-08-19",
        "baselineDays": 7,
        "amountMinorUnits": 15000,
        "ronEquivalentMinorUnits": 78884,
        "ronBaselineMinorUnits": 77700,
        "ronCurrency": "RON",
        "sourceName": "Banca Națională a României",
        "sourceUrl": "https://www.bnr.ro/23988-cursurile-pietei-valutare-in-format-xml",
        "shortText": f"{currency} +1,5% în 7 zile",
        "longText": (
            "EUR a crescut cu 1,5% în 7 zile — soldul tău de {amount} "
            "valorează acum {ron}, față de {ronBefore}."
        ),
        "shortTextEn": f"{currency} +1.5% in 7 days",
        "longTextEn": (
            "EUR rose 1.5% in 7 days — your {amount} is now worth {ron}, "
            "vs {ronBefore} before."
        ),
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
        return FakeCursor(
            [
                row
                for row in self.documents
                if all(row.get(field) == value for field, value in query.items())
            ]
        )


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
) -> tuple[FxInsightsService, dict[str, Any]]:
    recorder: dict[str, Any] = {}
    monkeypatch.setattr("backend.fx.service.get_db", lambda: FakeDB(documents, recorder))
    config = settings.model_copy(
        update={"fx_insights_source": SOURCE, "fx_insights_limit": limit}
    )
    return FxInsightsService(config=config), recorder


async def test_an_fx_insight_never_leaks_to_another_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = [notification("EUR", "2026-08-26", identifier="a")]
    service, _ = service_over(monkeypatch, documents)

    mine = await service.board_for_user(GABRIELA)
    theirs = await service.board_for_user(MARIA)

    assert [row.currency for row in mine.insights] == ["EUR"]
    assert theirs.insights == []
    assert theirs.total == 0


async def test_the_query_is_scoped_to_the_caller_and_to_the_bnr_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = [notification("EUR", "2026-08-26", identifier="a")]
    service, recorder = service_over(monkeypatch, documents)

    await service.board_for_user(GABRIELA)

    assert recorder["query"]["userId"] == GABRIELA
    assert recorder["query"]["source"] == SOURCE


async def test_the_card_shows_the_newest_move_per_currency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = [
        notification("EUR", "2026-08-26", identifier="newest"),
        notification("EUR", "2026-08-12", identifier="older"),
        notification("USD", "2026-08-20", identifier="usd"),
    ]
    service, _ = service_over(monkeypatch, documents)

    board = await service.board_for_user(GABRIELA)

    assert [row.currency for row in board.insights] == ["EUR", "USD"]
    assert board.insights[0].id == "newest"
    assert board.total == 3


async def test_the_configured_limit_caps_the_card_but_not_the_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = [
        notification("EUR", "2026-08-26", identifier="a"),
        notification("USD", "2026-08-26", identifier="b"),
        notification("EUR", "2026-08-12", identifier="c"),
    ]
    service, _ = service_over(monkeypatch, documents, limit=1)

    board = await service.board_for_user(GABRIELA)

    assert len(board.insights) == 1
    assert len(board.history) == 3


def test_money_reaches_the_wire_as_minor_units_and_a_currency_code() -> None:
    insight = to_insight(notification("EUR", "2026-08-26", identifier="a"))

    assert insight.amountMinorUnits == 15000
    assert insight.currency == "EUR"
    assert insight.ronEquivalentMinorUnits == 78884
    assert insight.ronBaselineMinorUnits == 77700
    assert insight.ronCurrency == "RON"
    assert "{amount}" in (insight.longText or "")
    assert "{ron}" in (insight.longText or "")
    assert "{ronBefore}" in (insight.longText or "")
    assert insight.sourceName == "Banca Națională a României"
    assert (insight.sourceUrl or "").startswith("https://www.bnr.ro/")
    assert insight.createdAt == "2026-08-26T12:00:00+00:00"


def test_the_dedupe_keeps_the_first_row_of_each_currency() -> None:
    rows = [
        {"currency": "EUR", "_id": "first"},
        {"currency": "EUR", "_id": "second"},
        {"currency": "USD", "_id": "third"},
        {"currency": None, "_id": "skipped"},
    ]

    assert [row["_id"] for row in newest_per_currency(rows, 5)] == ["first", "third"]


def test_one_rate_move_is_listed_once_in_the_history() -> None:
    rows = [
        {"currency": "EUR", "signalDate": "2026-08-26", "_id": "a"},
        {"currency": "EUR", "signalDate": "2026-08-26", "_id": "duplicate"},
        {"currency": "EUR", "signalDate": "2026-08-12", "_id": "b"},
    ]

    assert [row["_id"] for row in one_per_currency_signal(rows)] == ["a", "b"]
