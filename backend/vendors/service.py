from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict

from backend.config import Settings, settings
from backend.database.mongo import get_db
from backend.vendors.decision_engine import NOTIFICATIONS_COLLECTION
from backend.vendors.detector import CONFIRMED

NOTIFICATION_SCAN_LIMIT = 50


class InsightsBoard(BaseModel):
    model_config = ConfigDict(frozen=True)

    insights: list["VendorInsight"]
    history: list["VendorInsight"]
    total: int


class VendorInsight(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    source: str | None
    vendorNormalized: str | None
    vendorDisplayName: str | None
    vendorCategory: str | None
    currency: str | None
    month: str | None
    alertType: str | None
    confidence: str | None
    origin: str | None
    percentChange: float | None
    vendorPercentChange: float | None
    baselineMinorUnits: int | None
    observedMinorUnits: int | None
    shortText: str | None
    longText: str | None
    shortTextEn: str | None
    longTextEn: str | None
    newsEventKey: str | None
    newsPublishers: list[str]
    newsUrls: list[str]
    newsEffectiveDate: str | None
    newsMarket: str | None
    status: str | None
    createdAt: str | None


def _iso(value: Any) -> str | None:
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return value if isinstance(value, str) else None


def to_insight(document: dict[str, Any]) -> VendorInsight:
    return VendorInsight(
        id=str(document.get("_id", "")),
        source=document.get("source"),
        vendorNormalized=document.get("vendorNormalized"),
        vendorDisplayName=document.get("vendorDisplayName"),
        vendorCategory=document.get("vendorCategory"),
        currency=document.get("currency"),
        month=document.get("month"),
        alertType=document.get("alertType"),
        confidence=document.get("confidence"),
        origin=document.get("origin"),
        percentChange=document.get("percentChange"),
        vendorPercentChange=document.get("vendorPercentChange"),
        baselineMinorUnits=document.get("baselineMinorUnits"),
        observedMinorUnits=document.get("observedMinorUnits"),
        shortText=document.get("shortText"),
        longText=document.get("longText"),
        shortTextEn=document.get("shortTextEn"),
        longTextEn=document.get("longTextEn"),
        newsEventKey=document.get("newsEventKey"),
        newsPublishers=list(document.get("newsPublishers") or []),
        newsUrls=list(document.get("newsUrls") or []),
        newsEffectiveDate=document.get("newsEffectiveDate"),
        newsMarket=document.get("newsMarket"),
        status=document.get("status"),
        createdAt=_iso(document.get("createdAt")),
    )


def newest_per_vendor(
    documents: list[dict[str, Any]], limit: int
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    kept: list[dict[str, Any]] = []
    for document in documents:
        vendor = document.get("vendorNormalized")
        if not vendor or vendor in seen:
            continue
        seen.add(vendor)
        kept.append(document)
        if len(kept) >= limit:
            break
    return kept


def one_per_vendor_month(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chosen: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for document in documents:
        vendor = document.get("vendorNormalized")
        month = document.get("month")
        if not vendor or not month:
            continue
        key = (vendor, month)
        if key not in chosen:
            chosen[key] = document
            order.append(key)
            continue
        if (
            chosen[key].get("alertType") != CONFIRMED
            and document.get("alertType") == CONFIRMED
        ):
            chosen[key] = document
    return [chosen[key] for key in order]


class VendorInsightsService:
    def __init__(self, config: Settings) -> None:
        self._config = config

    async def _fetch(self, user_id: str) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"userId": user_id}
        if self._config.vendor_insights_source:
            query["source"] = self._config.vendor_insights_source

        return (
            await get_db()[NOTIFICATIONS_COLLECTION]
            .find(query)
            .sort([("month", -1), ("createdAt", -1)])
            .to_list(length=NOTIFICATION_SCAN_LIMIT)
        )

    async def list_for_user(
        self, user_id: str, limit: int | None = None
    ) -> list[VendorInsight]:
        documents = await self._fetch(user_id)
        capped = limit if limit is not None else self._config.vendor_insights_limit
        return [
            to_insight(document)
            for document in newest_per_vendor(documents, max(capped, 0))
        ]

    async def board_for_user(
        self, user_id: str, limit: int | None = None
    ) -> InsightsBoard:
        documents = await self._fetch(user_id)
        capped = limit if limit is not None else self._config.vendor_insights_limit
        return InsightsBoard(
            insights=[
                to_insight(document)
                for document in newest_per_vendor(documents, max(capped, 0))
            ],
            history=[
                to_insight(document) for document in one_per_vendor_month(documents)
            ],
            total=len(one_per_vendor_month(documents)),
        )


@lru_cache(maxsize=1)
def get_vendor_insights_service() -> VendorInsightsService:
    return VendorInsightsService(config=settings)
