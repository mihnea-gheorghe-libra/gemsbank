from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict

from backend.config import Settings, settings
from backend.database.mongo import get_db
from backend.fx.signals import NOTIFICATIONS_COLLECTION

USERS_COLLECTION = "users"
NOTIFICATION_SCAN_LIMIT = 50


class FxInsight(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    source: str | None
    currency: str | None
    signalDate: str | None
    signalKey: str | None
    direction: str | None
    changePercent: float | None
    baselineRate: int | None
    currentRate: int | None
    baselineDate: str | None
    baselineDays: int | None
    amountMinorUnits: int | None
    ronEquivalentMinorUnits: int | None
    ronBaselineMinorUnits: int | None
    ronCurrency: str | None
    sourceName: str | None
    sourceUrl: str | None
    shortText: str | None
    longText: str | None
    shortTextEn: str | None
    longTextEn: str | None
    status: str | None
    createdAt: str | None


class FxInsightsBoard(BaseModel):
    model_config = ConfigDict(frozen=True)

    insights: list[FxInsight]
    history: list[FxInsight]
    total: int


def _iso(value: Any) -> str | None:
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return value if isinstance(value, str) else None


def to_insight(document: dict[str, Any]) -> FxInsight:
    return FxInsight(
        id=str(document.get("_id", "")),
        source=document.get("source"),
        currency=document.get("currency"),
        signalDate=document.get("signalDate"),
        signalKey=document.get("signalKey"),
        direction=document.get("direction"),
        changePercent=document.get("changePercent"),
        baselineRate=document.get("baselineRate"),
        currentRate=document.get("currentRate"),
        baselineDate=document.get("baselineDate"),
        baselineDays=document.get("baselineDays"),
        amountMinorUnits=document.get("amountMinorUnits"),
        ronEquivalentMinorUnits=document.get("ronEquivalentMinorUnits"),
        ronBaselineMinorUnits=document.get("ronBaselineMinorUnits"),
        ronCurrency=document.get("ronCurrency"),
        sourceName=document.get("sourceName"),
        sourceUrl=document.get("sourceUrl"),
        shortText=document.get("shortText"),
        longText=document.get("longText"),
        shortTextEn=document.get("shortTextEn"),
        longTextEn=document.get("longTextEn"),
        status=document.get("status"),
        createdAt=_iso(document.get("createdAt")),
    )


def newest_per_currency(
    documents: list[dict[str, Any]], limit: int
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    kept: list[dict[str, Any]] = []
    for document in documents:
        currency = document.get("currency")
        if not currency or currency in seen:
            continue
        seen.add(currency)
        kept.append(document)
        if len(kept) >= limit:
            break
    return kept


def one_per_currency_signal(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chosen: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for document in documents:
        currency = document.get("currency")
        signal_date = document.get("signalDate")
        if not currency or not signal_date:
            continue
        key = (currency, signal_date)
        if key not in chosen:
            chosen[key] = document
            order.append(key)
    return [chosen[key] for key in order]


class FxInsightsService:
    def __init__(self, config: Settings) -> None:
        self._config = config

    async def resolve_user_id(self, username: str | None) -> str | None:
        if not username or not username.strip():
            return None
        user = await get_db()[USERS_COLLECTION].find_one({"username": username.strip()})
        if not user or not user.get("_id"):
            return None
        return str(user["_id"])

    async def _fetch(self, username: str | None) -> list[dict[str, Any]]:
        user_id = await self.resolve_user_id(username)
        if user_id is None:
            return []

        query: dict[str, Any] = {"userId": user_id}
        if self._config.fx_insights_source:
            query["source"] = self._config.fx_insights_source

        return (
            await get_db()[NOTIFICATIONS_COLLECTION]
            .find(query)
            .sort([("signalDate", -1), ("createdAt", -1)])
            .to_list(length=NOTIFICATION_SCAN_LIMIT)
        )

    async def board_for_username(
        self, username: str | None, limit: int | None = None
    ) -> FxInsightsBoard:
        documents = await self._fetch(username)
        capped = limit if limit is not None else self._config.fx_insights_limit
        history = one_per_currency_signal(documents)
        return FxInsightsBoard(
            insights=[
                to_insight(document)
                for document in newest_per_currency(documents, max(capped, 0))
            ],
            history=[to_insight(document) for document in history],
            total=len(history),
        )


@lru_cache(maxsize=1)
def get_fx_insights_service() -> FxInsightsService:
    return FxInsightsService(config=settings)
