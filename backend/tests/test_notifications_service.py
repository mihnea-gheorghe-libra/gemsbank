from datetime import UTC, datetime
from typing import Any

import pytest

from backend.helpers.context import Actor
from backend.notifications.service import NotificationsService

GABRIELA = "01a01ed4-99bc-728d-8a58-a239b290a161"
MARIA = "01a01ed4-99bc-728d-8a58-a239b290a162"


def _matches(document: dict[str, Any], query: dict[str, Any]) -> bool:
    for key, condition in query.items():
        if key == "$or":
            if not any(_matches(document, sub) for sub in condition):
                return False
            continue
        value: Any = document
        for part in key.split("."):
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(part)
        if isinstance(condition, dict) and "$in" in condition:
            if value not in condition["$in"]:
                return False
        elif value != condition:
            return False
    return True


class FakeCursor:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self._items = items

    def sort(self, field: str, direction: int) -> "FakeCursor":
        self._items = sorted(self._items, key=lambda d: d[field], reverse=direction < 0)
        return self

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        return self._items[:length] if length is not None else self._items


class FakeCollection:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self._documents = documents

    def find(self, query: dict[str, Any]) -> FakeCursor:
        return FakeCursor([doc for doc in self._documents if _matches(doc, query)])


class FakeDB:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self._documents = documents

    def __getitem__(self, name: str) -> FakeCollection:
        return FakeCollection(self._documents)


class FakeAuth:
    def __init__(self, prefs: dict[str, Any] | None = None) -> None:
        self._prefs = prefs or {}

    async def get_me(self, user_id: str) -> dict[str, Any]:
        return {"prefs": self._prefs}


def _event(
    name: str,
    actor_kind: str = "user",
    actor_id: str | None = None,
    on_behalf_of: str | None = None,
    payload: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
    doc_id: str = "e1",
) -> dict[str, Any]:
    return {
        "_id": doc_id,
        "name": name,
        "payload": payload or {},
        "actorKind": actor_kind,
        "actorId": actor_id,
        "onBehalfOf": on_behalf_of,
        "occurredAt": occurred_at or datetime(2026, 1, 1, tzinfo=UTC),
    }


def service_over(
    monkeypatch: pytest.MonkeyPatch,
    documents: list[dict[str, Any]],
    prefs: dict[str, Any] | None = None,
) -> NotificationsService:
    monkeypatch.setattr(
        "backend.notifications.service.get_db", lambda: FakeDB(documents)
    )
    return NotificationsService(auth=FakeAuth(prefs))


@pytest.mark.anyio
async def test_a_self_initiated_event_is_scoped_to_its_own_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = [
        _event("payments.transfer_posted", actor_kind="user", actor_id=GABRIELA, doc_id="a")
    ]
    service = service_over(monkeypatch, documents)

    mine = await service.board_for_user(Actor(kind="user", id=GABRIELA))
    theirs = await service.board_for_user(Actor(kind="user", id=MARIA))

    assert [n.type for n in mine.notifications] == ["transaction_accepted"]
    assert theirs.notifications == []


@pytest.mark.anyio
async def test_an_admin_initiated_event_is_scoped_via_the_payload_user_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = [
        _event(
            "admin.credit_approved",
            actor_kind="admin",
            actor_id="admin",
            payload={"userId": GABRIELA, "reason": "income verified"},
            doc_id="a",
        )
    ]
    service = service_over(monkeypatch, documents)

    mine = await service.board_for_user(Actor(kind="user", id=GABRIELA))
    theirs = await service.board_for_user(Actor(kind="user", id=MARIA))

    assert [n.type for n in mine.notifications] == ["credit_approved"]
    assert theirs.notifications == []


@pytest.mark.anyio
async def test_a_system_run_event_on_behalf_of_a_user_is_scoped_to_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = [
        _event(
            "goals.achieved",
            actor_kind="system",
            actor_id="standing-orders-job",
            on_behalf_of=GABRIELA,
            payload={"userId": GABRIELA, "name": "Apartment"},
            doc_id="a",
        )
    ]
    service = service_over(monkeypatch, documents)

    mine = await service.board_for_user(Actor(kind="user", id=GABRIELA))
    theirs = await service.board_for_user(Actor(kind="user", id=MARIA))

    assert [n.type for n in mine.notifications] == ["goal_achieved"]
    assert theirs.notifications == []


@pytest.mark.anyio
async def test_events_not_on_the_whitelist_never_appear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = [
        _event("auth.signed_in", actor_kind="user", actor_id=GABRIELA, doc_id="a"),
    ]
    service = service_over(monkeypatch, documents)

    board = await service.board_for_user(Actor(kind="user", id=GABRIELA))

    assert board.notifications == []


@pytest.mark.anyio
async def test_unread_count_follows_the_seen_at_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = [
        _event(
            "payments.transfer_posted",
            actor_kind="user",
            actor_id=GABRIELA,
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            doc_id="old",
        ),
        _event(
            "payments.transfer_posted",
            actor_kind="user",
            actor_id=GABRIELA,
            occurred_at=datetime(2026, 1, 3, tzinfo=UTC),
            doc_id="new",
        ),
    ]
    service = service_over(
        monkeypatch, documents, prefs={"notificationsSeenAt": "2026-01-02T00:00:00+00:00"}
    )

    board = await service.board_for_user(Actor(kind="user", id=GABRIELA))

    assert board.unreadCount == 1
    by_id = {n.id: n.read for n in board.notifications}
    assert by_id == {"old": True, "new": False}


@pytest.mark.anyio
async def test_no_seen_at_cursor_means_everything_is_unread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = [
        _event("payments.transfer_posted", actor_kind="user", actor_id=GABRIELA, doc_id="a")
    ]
    service = service_over(monkeypatch, documents)

    board = await service.board_for_user(Actor(kind="user", id=GABRIELA))

    assert board.unreadCount == 1
    assert board.notifications[0].read is False


@pytest.mark.anyio
async def test_the_limit_caps_how_many_notifications_come_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = [
        _event(
            "payments.transfer_posted",
            actor_kind="user",
            actor_id=GABRIELA,
            occurred_at=datetime(2026, 1, day, tzinfo=UTC),
            doc_id=f"d{day}",
        )
        for day in range(1, 6)
    ]
    service = service_over(monkeypatch, documents)

    board = await service.board_for_user(Actor(kind="user", id=GABRIELA), limit=2)

    assert len(board.notifications) == 2
    assert board.notifications[0].id == "d5"
