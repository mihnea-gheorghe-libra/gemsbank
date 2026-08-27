from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field
from pymongo import AsyncMongoClient, UpdateOne

from backend.config import settings
from backend.vendors.decision_engine import vendor_profiles
from backend.vendors.extractor import STATS_COLLECTION, load_mongo_settings
from backend.vendors.news_sources import (
    GNEWS,
    GOOGLE_NEWS,
    RequestThrottle,
    build_query,
    fetch_gnews,
    fetch_google_news,
    fold,
    merge_sources,
)

SEEN_COLLECTION = "newsArticlesSeen"
SIGNALS_COLLECTION = "newsSignals"
SEEN_UNIQUE_KEY = ("vendorNormalized", "articleKey")
SIGNAL_UNIQUE_KEY = ("vendorNormalized", "articleUrl")

KEYWORDS = (
    "scump",
    "pret",
    "tarif",
    "abonament",
    "factura",
    "majorare",
    "creste",
    "crestere",
    "ieftin",
    "price",
    "prices",
    "increase",
    "hike",
    "raise",
    "raises",
    "subscription",
    "tariff",
    "bill",
    "cost",
)

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

SYSTEM_PROMPT = (
    "You classify news reports about consumer price changes for a Romanian bank. "
    "You answer with a single JSON object and nothing else. "
    "Only set confirms_increase to true when the report states that this specific "
    "vendor raised, or announced it will raise, the price customers pay. "
    "A report about the company's revenue, stock, content, outages or a competitor "
    "is not a price increase. A price cut is not an increase. "
    "Never copy the wording you are given; write summary as your own short paraphrase, ""at most 25 words. Read percent_increase, effective_date and market out of the ""summary text when it is stated there, not only out of the headline. "
    "Fields: confirms_increase (boolean), percent_increase (number or null), "
    "effective_date (YYYY-MM-DD or null), market (ISO country code, 'global', or null), "
    "confidence ('low'|'medium'|'high'), summary (string)."
)


class WatcherConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_collection: str = "payments_seed_seasonal"
    stats_collection: str = STATS_COLLECTION
    seen_collection: str = SEEN_COLLECTION
    signals_collection: str = SIGNALS_COLLECTION
    languages: tuple[str, ...] = ("ro", "en")
    apis: tuple[str, ...] = (GNEWS, GOOGLE_NEWS)
    vendors: tuple[str, ...] = ()
    max_articles_per_vendor: int = 25
    max_llm_calls: int = 20
    request_timeout_seconds: float = 20.0
    dry_run: bool = False
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def matched_keywords(*parts: str) -> list[str]:
    haystack = fold(" ".join(part for part in parts if part))
    return sorted({keyword for keyword in KEYWORDS if keyword in haystack})


def parse_classification(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        _, _, text = text.partition("\n")
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    if not isinstance(payload.get("confirms_increase"), bool):
        return None

    percent = payload.get("percent_increase")
    if not isinstance(percent, (int, float)) or isinstance(percent, bool):
        percent = None
    confidence = payload.get("confidence")
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"
    effective = payload.get("effective_date")
    if not isinstance(effective, str) or not effective.strip():
        effective = None
    market = payload.get("market")
    if not isinstance(market, str) or not market.strip():
        market = None
    summary = payload.get("summary")
    summary = summary.strip() if isinstance(summary, str) else ""

    return {
        "confirms_increase": payload["confirms_increase"],
        "percent_increase": percent,
        "effective_date": effective,
        "market": market,
        "confidence": confidence,
        "summary": summary[:400],
    }


async def classify(
    client: httpx.AsyncClient, display_name: str, article: dict[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    endpoint = (settings.azure_openai_endpoint or "").rstrip("/")
    deployment = settings.azure_openai_deployment_name
    api_key = settings.azure_openai_api_key
    if not endpoint or not deployment or not api_key:
        return None, "azure_openai_not_configured"

    published = (
        article["publishedAt"].date().isoformat() if article["publishedAt"] else "unknown"
    )
    lines = [
        f"Vendor: {display_name}",
        f"Publisher: {article['publisher'] or 'unknown'}",
        f"Publisher country: {article.get('publisherCountry') or 'unknown'}",
        f"Published: {published}",
        f"Headline: {article['title']}",
    ]
    if article.get("description"):
        lines.append(f"Summary: {article['description']}")
    user_prompt = "\n".join(lines)

    try:
        response = await client.post(
            f"{endpoint}/openai/deployments/{deployment}/chat/completions",
            params={"api-version": settings.azure_openai_api_version},
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
                "max_completion_tokens": 2000,
            },
        )
    except httpx.HTTPError as error:
        return None, f"transport_error:{type(error).__name__}"

    if response.status_code != 200:
        return None, f"http_{response.status_code}"

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError, json.JSONDecodeError):
        return None, "unreadable_response"

    parsed = parse_classification(content or "")
    if parsed is None:
        return None, "malformed_json"
    return parsed, None


async def vendor_display_names(db: Any, config: WatcherConfig) -> list[tuple[str, str]]:
    rows = await db[config.stats_collection].find(
        {"source": config.source_collection}
    ).to_list(length=None)
    profiles = vendor_profiles(rows)
    names: dict[str, str] = {}
    for (vendor, _currency), profile in profiles.items():
        names.setdefault(vendor, profile["displayName"])
    selected = sorted(names.items())
    if config.vendors:
        wanted = {value.upper() for value in config.vendors}
        selected = [row for row in selected if row[0] in wanted]
    return selected


async def ensure_collections(db: Any, config: WatcherConfig) -> None:
    await db[config.seen_collection].create_index(
        [(field, 1) for field in SEEN_UNIQUE_KEY], unique=True, name="article_seen_unique"
    )
    await db[config.seen_collection].create_index([("vendorNormalized", 1), ("firstSeenAt", -1)])
    await db[config.signals_collection].create_index(
        [(field, 1) for field in SIGNAL_UNIQUE_KEY], unique=True, name="news_signal_unique"
    )
    await db[config.signals_collection].create_index([("vendorNormalized", 1), ("publishedAt", -1)])


async def run(db: Any, config: WatcherConfig) -> dict[str, Any]:
    await ensure_collections(db, config)
    vendors = await vendor_display_names(db, config)

    stats: dict[str, dict[str, int]] = {}
    signals: list[dict[str, Any]] = []
    seen_writes: list[UpdateOne] = []
    llm_budget = config.max_llm_calls
    failures: list[dict[str, str]] = []
    source_errors: list[dict[str, str]] = []
    throttle = RequestThrottle(settings.gnews_min_request_interval_seconds)

    async with httpx.AsyncClient(
        timeout=config.request_timeout_seconds,
        follow_redirects=True,
        headers={"User-Agent": BROWSER_UA},
    ) as client:
        for vendor, display_name in vendors:
            counters = {
                "from_gnews": 0,
                "from_google_news": 0,
                "cross_source_duplicates": 0,
                "with_description": 0,
                "found": 0,
                "already_seen": 0,
                "keyword_rejected": 0,
                "budget_skipped": 0,
                "sent_to_llm": 0,
                "confirmed": 0,
                "llm_failed": 0,
            }
            stats[vendor] = counters

            groups: list[list[dict[str, Any]]] = []
            for language in config.languages:
                if GNEWS in config.apis:
                    rows, error = await fetch_gnews(
                        client,
                        display_name,
                        language,
                        config.max_articles_per_vendor,
                        throttle,
                    )
                    if error:
                        source_errors.append({"vendor": vendor, "reason": error})
                    else:
                        counters["from_gnews"] += len(rows)
                        groups.append(rows)
                if GOOGLE_NEWS in config.apis:
                    rows = await fetch_google_news(client, display_name, language)
                    counters["from_google_news"] += len(rows)
                    groups.append(rows)

            merged = merge_sources(*groups)
            counters["cross_source_duplicates"] = (
                counters["from_gnews"] + counters["from_google_news"] - len(merged)
            )
            ordered = sorted(
                merged,
                key=lambda row: row["publishedAt"] or datetime.min.replace(tzinfo=UTC),
                reverse=True,
            )[: config.max_articles_per_vendor]
            counters["found"] = len(ordered)
            counters["with_description"] = sum(
                1 for row in ordered if row["description"]
            )

            known = {
                row["articleKey"]
                for row in await db[config.seen_collection]
                .find(
                    {"vendorNormalized": vendor},
                    {"articleKey": 1, "_id": 0},
                )
                .to_list(length=None)
            }

            for article in ordered:
                if article["dedupeKey"] in known:
                    counters["already_seen"] += 1
                    continue

                keywords = matched_keywords(article["title"], article["description"])
                record: dict[str, Any] = {
                    "vendorNormalized": vendor,
                    "articleKey": article["dedupeKey"],
                    "articleUrl": article["url"],
                    "publisher": article["publisher"],
                    "publisherCountry": article.get("publisherCountry"),
                    "publishedAt": article["publishedAt"],
                    "language": article["language"],
                    "sourceApi": article["sourceApi"],
                    "alsoFoundBy": article.get("alsoFoundBy", []),
                    "hadDescription": bool(article["description"]),
                    "titleHash": hashlib.sha256(
                        article["title"].encode("utf-8")
                    ).hexdigest(),
                    "matchedKeywords": keywords,
                    "passedKeywordFilter": bool(keywords),
                    "sentToLlm": False,
                    "llmOutcome": None,
                    "firstSeenAt": config.generated_at,
                }

                if not keywords:
                    counters["keyword_rejected"] += 1
                    if not config.dry_run:
                        seen_writes.append(_upsert_seen(record))
                    continue

                if config.dry_run:
                    counters["budget_skipped"] += 1
                    continue

                if llm_budget <= 0:
                    counters["budget_skipped"] += 1
                    continue

                llm_budget -= 1
                counters["sent_to_llm"] += 1
                verdict, error = await classify(client, display_name, article)
                record["sentToLlm"] = True

                if verdict is None:
                    counters["llm_failed"] += 1
                    record["llmOutcome"] = error
                    failures.append({"vendor": vendor, "reason": error or "unknown"})
                    seen_writes.append(_upsert_seen(record))
                    continue

                record["llmOutcome"] = (
                    "confirmed" if verdict["confirms_increase"] else "not_an_increase"
                )
                seen_writes.append(_upsert_seen(record))

                if not verdict["confirms_increase"]:
                    continue

                counters["confirmed"] += 1
                signals.append(
                    {
                        "vendorNormalized": vendor,
                        "vendorDisplayName": display_name,
                        "articleUrl": article["url"],
                        "publisher": article["publisher"],
                        "publisherCountry": article.get("publisherCountry"),
                        "sourceApi": article["sourceApi"],
                        "hadDescription": bool(article["description"]),
                        "publishedAt": article["publishedAt"],
                        "percentIncrease": verdict["percent_increase"],
                        "effectiveDate": verdict["effective_date"],
                        "market": verdict["market"],
                        "confidence": verdict["confidence"],
                        "summary": verdict["summary"],
                        "language": article["language"],
                        "source": article["sourceApi"],
                        "foundAt": config.generated_at,
                    }
                )

    if seen_writes:
        await db[config.seen_collection].bulk_write(seen_writes, ordered=False)
    if signals:
        await db[config.signals_collection].bulk_write(
            [
                UpdateOne(
                    {field: row[field] for field in SIGNAL_UNIQUE_KEY},
                    {"$set": row},
                    upsert=True,
                )
                for row in signals
            ],
            ordered=False,
        )

    return {
        "vendors": vendors,
        "stats": stats,
        "signals": signals,
        "failures": failures,
        "source_errors": source_errors,
        "llm_calls_used": config.max_llm_calls - llm_budget,
    }


def _upsert_seen(record: dict[str, Any]) -> UpdateOne:
    return UpdateOne(
        {field: record[field] for field in SEEN_UNIQUE_KEY},
        {"$set": record},
        upsert=True,
    )


def llm_budget_label(config: WatcherConfig) -> str:
    return "dry run, no calls" if config.dry_run else str(config.max_llm_calls)


def report(outcome: dict[str, Any], config: WatcherConfig) -> None:
    print(f"\nsource        : {config.source_collection}")
    print(f"sources       : {','.join(config.apis)}  languages={','.join(config.languages)}")
    print(f"llm budget    : {llm_budget_label(config)}")
    print(f"llm calls used: {outcome['llm_calls_used']}\n")

    header = (
        f"{'vendor':<22}{'gnews':>7}{'gnews_rss':>10}{'dupes':>7}{'kept':>6}"
        f"{'w/desc':>8}{'seen':>6}{'no kw':>7}{'skip':>6}{'toLLM':>7}"
        f"{'fail':>6}{'conf':>6}"
    )
    print(header)
    print("-" * len(header))
    for vendor, _display in outcome["vendors"]:
        counters = outcome["stats"][vendor]
        print(
            f"{vendor:<22}{counters['from_gnews']:>7}"
            f"{counters['from_google_news']:>10}"
            f"{counters['cross_source_duplicates']:>7}{counters['found']:>6}"
            f"{counters['with_description']:>8}{counters['already_seen']:>6}"
            f"{counters['keyword_rejected']:>7}{counters['budget_skipped']:>6}"
            f"{counters['sent_to_llm']:>7}{counters['llm_failed']:>6}"
            f"{counters['confirmed']:>6}"
        )

    if outcome["source_errors"]:
        print()
        print("source errors (job continued on the remaining sources):")
        for row in outcome["source_errors"]:
            print(f"  {row['vendor']:<22} {row['reason']}")

    filled = [
        signal
        for signal in outcome["signals"]
        if signal["percentIncrease"] is not None
    ]
    if outcome["signals"]:
        print()
        print(
            f"field completeness: percent {len(filled)}/{len(outcome['signals'])}"
            f"  date {sum(1 for s in outcome['signals'] if s['effectiveDate'])}"
            f"/{len(outcome['signals'])}"
            f"  market {sum(1 for s in outcome['signals'] if s['market'])}"
            f"/{len(outcome['signals'])}"
        )

    if outcome["failures"]:
        print("\nllm failures (pipeline continued):")
        for failure in outcome["failures"]:
            print(f"  {failure['vendor']:<22} {failure['reason']}")

    print(f"\nconfirmed signals written: {len(outcome['signals'])}")
    for signal in outcome["signals"]:
        percent = (
            f"{signal['percentIncrease']}%"
            if signal["percentIncrease"] is not None
            else "unspecified"
        )
        print(
            f"  {signal['vendorNormalized']:<22} {percent:<12} "
            f"effective {signal['effectiveDate'] or 'unknown':<12} "
            f"market {signal['market'] or 'unknown':<8} "
            f"confidence {signal['confidence']}"
        )
        print(f"     {signal['summary']}")
        print(f"     {signal['articleUrl'][:110]}")


async def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="payments_seed_seasonal")
    parser.add_argument("--vendor", action="append", default=None)
    parser.add_argument("--languages", default="ro,en")
    parser.add_argument("--max-articles-per-vendor", type=int, default=25)
    parser.add_argument("--max-llm-calls", type=int, default=20)
    parser.add_argument("--sources", default="gnews,google_news")
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()

    config = WatcherConfig(
        source_collection=arguments.source,
        vendors=tuple(arguments.vendor or ()),
        languages=tuple(
            part.strip() for part in arguments.languages.split(",") if part.strip()
        ),
        max_articles_per_vendor=arguments.max_articles_per_vendor,
        max_llm_calls=arguments.max_llm_calls,
        apis=tuple(
            part.strip() for part in arguments.sources.split(",") if part.strip()
        ),
        dry_run=arguments.dry_run,
    )

    if GNEWS in config.apis:
        key = settings.gnews_api_key or ""
        print(
            f"gnews key     : {'set' if key else 'MISSING'}, length={len(key)}, "
            f"endpoint={settings.gnews_base_url}, "
            f"min interval={settings.gnews_min_request_interval_seconds}s"
        )

    if GNEWS in config.apis and not settings.gnews_api_key:
        print(
            "GNEWS_API_KEY is not set. Add it to .env (get a free key at gnews.io), "
            "or run with --sources google_news to use the RSS feed alone — "
            "headlines only, no article summary."
        )
        return 2

    if not config.dry_run and not (
        settings.azure_openai_endpoint
        and settings.azure_openai_api_key
        and settings.azure_openai_deployment_name
    ):
        print(
            "AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY and "
            "AZURE_OPENAI_DEPLOYMENT_NAME must be set; use --dry-run to skip the LLM step"
        )
        return 2

    uri, db_name = load_mongo_settings()
    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(
        uri, uuidRepresentation="standard", tz_aware=True, serverSelectionTimeoutMS=10000
    )
    try:
        outcome = await run(client[db_name], config)
        report(outcome, config)
    finally:
        await client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
