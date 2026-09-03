from datetime import datetime
from functools import lru_cache
from typing import Any, Protocol

from pydantic import BaseModel

from backend.auth.service import get_auth_service
from backend.database.mongo import get_db
from backend.helpers.context import Actor
from backend.notifications import validation

OUTBOX_COLLECTION = "outbox"
SEEN_AT_PREF = "notificationsSeenAt"

EVENT_TYPES: dict[str, str] = {
    "admin.credit_approved": "credit_approved",
    "admin.credit_rejected": "credit_rejected",
    "payments.transfer_posted": "transaction_accepted",
    "admin.account_frozen": "account_frozen",
    "cards.frozen": "card_frozen",
    "goals.achieved": "goal_achieved",
    "goals.invite_sent": "goal_invite_sent",
    "goals.invite_responded": "goal_invite_responded",
    "goals.invite_accepted": "goal_invite_accepted",
    "goals.invite_declined": "goal_invite_declined",
}


class ProfileReader(Protocol):
    async def get_me(self, user_id: str) -> dict[str, Any]: ...


class Notification(BaseModel):
    id: str
    type: str
    occurredAt: str
    payload: dict[str, Any]
    read: bool


class NotificationsBoard(BaseModel):
    notifications: list[Notification]
    unreadCount: int


def _to_notification(document: dict[str, Any], seen_at: datetime | None) -> Notification:
    occurred_at: datetime = document["occurredAt"]
    return Notification(
        id=document["_id"],
        type=EVENT_TYPES[document["name"]],
        occurredAt=occurred_at.isoformat(),
        payload=document.get("payload") or {},
        read=seen_at is not None and occurred_at <= seen_at,
    )


class NotificationsService:
    def __init__(self, auth: ProfileReader) -> None:
        self._auth = auth

    async def board_for_user(
        self, actor: Actor, limit: int | None = None
    ) -> NotificationsBoard:
        user_id = actor.subject_id()
        capped = validation.normalise_limit(limit)
        query = {
            "name": {"$in": list(EVENT_TYPES)},
            "$or": [
                {"onBehalfOf": user_id},
                {"actorKind": "user", "actorId": user_id},
                {"payload.userId": user_id},
            ],
        }
        cursor = get_db()[OUTBOX_COLLECTION].find(query).sort("occurredAt", -1)
        documents = await cursor.to_list(length=capped)

        me = await self._auth.get_me(user_id)
        seen_at_raw = (me.get("prefs") or {}).get(SEEN_AT_PREF)
        seen_at = datetime.fromisoformat(seen_at_raw) if seen_at_raw else None

        notifications = [_to_notification(document, seen_at) for document in documents]
        unread = sum(1 for notification in notifications if not notification.read)
        return NotificationsBoard(notifications=notifications, unreadCount=unread)


@lru_cache(maxsize=1)
def get_notifications_service() -> NotificationsService:
    return NotificationsService(auth=get_auth_service())
