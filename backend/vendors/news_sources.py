from __future__ import annotations

import asyncio
import hashlib
import re
import time
import xml.etree.ElementTree as ElementTree
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from backend.config import settings
from backend.vendors.payments_adapter import DIACRITIC_FOLDING

GOOGLE_NEWS = "google_news"
GNEWS = "gnews"

GNEWS_RETRY_BACKOFF_SECONDS = (2.0, 5.0, 10.0)

FEED_URL = "https://news.google.com/rss/search"

LOCALES = {
    "ro": {"hl": "ro", "gl": "RO", "ceid": "RO:ro"},
    "en": {"hl": "en-US", "gl": "US", "ceid": "US:en"},
}

GNEWS_LOCALES = {
    "ro": {"lang": "ro", "country": "ro"},
    "en": {"lang": "en", "country": "us"},
}

QUERY_TEMPLATES = {
    "ro": "{vendor} scumpire pret abonament",
    "en": "{vendor} price increase subscription",
}

GNEWS_QUERY_TEMPLATES = {
    "ro": (
        '"{vendor}" AND (pret OR preț OR scumpire OR scumpit OR abonament '
        "OR tarif OR factura OR factură OR majorare)"
    ),
    "en": (
        '"{vendor}" AND (price OR prices OR subscription OR increase '
        "OR hike OR tariff OR bill)"
    ),
}

GNEWS_QUERY_MAX_CHARS = 200

TRACKING_PARAMETERS = re.compile(
    r"^(utm_|fbclid$|gclid$|igshid$|mc_cid$|mc_eid$|ref$|oc$|amp$)"
)
PUBLISHER_SEPARATORS = (" - ", " – ", " — ", " | ")
PUBLISHER_MAX_CHARS = 40
PUBLISHER_MAX_WORDS = 5
WHITESPACE = re.compile(r"\s+")


def fold(text: str) -> str:
    folded = text
    for source, replacement in DIACRITIC_FOLDING:
        folded = folded.replace(source, replacement)
    return folded.lower()


def strip_publisher_suffix(title: str) -> str:
    for separator in PUBLISHER_SEPARATORS:
        head, found, tail = title.rpartition(separator)
        if not found or not head.strip():
            continue
        candidate = tail.strip()
        if len(candidate) <= PUBLISHER_MAX_CHARS and (
            len(candidate.split()) <= PUBLISHER_MAX_WORDS
        ):
            return head.strip()
    return title.strip()


def normalise_title(title: str) -> str:
    return WHITESPACE.sub(" ", fold(strip_publisher_suffix(title.strip()))).strip()


def normalise_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/")
    keep = [
        pair
        for pair in parts.query.split("&")
        if pair and not TRACKING_PARAMETERS.match(pair.split("=")[0])
    ]
    return urlunsplit(("https", host, path, "&".join(sorted(keep)), ""))


def dedupe_key(title: str, url: str) -> str:
    normalised = normalise_title(title)
    basis = normalised if len(normalised) >= 20 else normalise_url(url)
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def build_query(display_name: str, language: str, api: str = GOOGLE_NEWS) -> str:
    if api != GNEWS:
        return QUERY_TEMPLATES[language].format(vendor=display_name)

    template = GNEWS_QUERY_TEMPLATES[language]
    room = GNEWS_QUERY_MAX_CHARS - len(template.format(vendor=""))
    vendor = display_name.replace('"', "").strip()[:room].strip()
    return template.format(vendor=vendor)


def make_article(
    *,
    title: str,
    description: str,
    url: str,
    published_at: datetime | None,
    publisher: str,
    publisher_country: str | None,
    language: str,
    api: str,
) -> dict[str, Any]:
    return {
        "title": title.strip(),
        "description": (description or "").strip(),
        "url": url,
        "publishedAt": published_at,
        "publisher": publisher,
        "publisherCountry": publisher_country,
        "language": language,
        "sourceApi": api,
        "dedupeKey": dedupe_key(title, url),
    }


def parse_google_news(xml_text: str, language: str) -> list[dict[str, Any]]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []

    articles: list[dict[str, Any]] = []
    for item in root.iter("item"):
        link = (item.findtext("link") or "").strip()
        title = (item.findtext("title") or "").strip()
        if not link or not title:
            continue
        published_raw = (item.findtext("pubDate") or "").strip()
        published_at: datetime | None = None
        if published_raw:
            try:
                published_at = parsedate_to_datetime(published_raw).astimezone(UTC)
            except (TypeError, ValueError):
                published_at = None
        source_node = item.find("source")
        publisher = (source_node.text or "").strip() if source_node is not None else ""
        articles.append(
            make_article(
                title=title,
                description="",
                url=link,
                published_at=published_at,
                publisher=publisher,
                publisher_country=None,
                language=language,
                api=GOOGLE_NEWS,
            )
        )
    return articles


def parse_gnews(payload: dict[str, Any], language: str) -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    for row in payload.get("articles") or []:
        if not isinstance(row, dict):
            continue
        title = (row.get("title") or "").strip()
        url = (row.get("url") or "").strip()
        if not title or not url:
            continue
        published_at: datetime | None = None
        raw = row.get("publishedAt")
        if isinstance(raw, str) and raw:
            try:
                published_at = datetime.fromisoformat(
                    raw.replace("Z", "+00:00")
                ).astimezone(UTC)
            except ValueError:
                published_at = None
        source = row.get("source") if isinstance(row.get("source"), dict) else {}
        articles.append(
            make_article(
                title=title,
                description=row.get("description") or "",
                url=url,
                published_at=published_at,
                publisher=(source.get("name") or "").strip(),
                publisher_country=(source.get("country") or None),
                language=row.get("lang") or language,
                api=GNEWS,
            )
        )
    return articles


class RequestThrottle:
    def __init__(self, min_interval_seconds: float) -> None:
        self._min_interval = min_interval_seconds
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._lock:
            elapsed = time.monotonic() - self._last
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last = time.monotonic()


async def fetch_google_news(
    client: httpx.AsyncClient, display_name: str, language: str
) -> list[dict[str, Any]]:
    params = {"q": build_query(display_name, language), **LOCALES[language]}
    try:
        response = await client.get(FEED_URL, params=params)
    except httpx.HTTPError:
        return []
    if response.status_code != 200:
        return []
    return parse_google_news(response.text, language)


def redact(text: str) -> str:
    key = settings.gnews_api_key
    cleaned = text.replace("\n", " ").strip()
    if key:
        cleaned = cleaned.replace(key, "***REDACTED***")
    return cleaned[:300]


async def fetch_gnews(
    client: httpx.AsyncClient,
    display_name: str,
    language: str,
    max_articles: int,
    throttle: RequestThrottle | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    api_key = settings.gnews_api_key
    if not api_key:
        return [], "gnews_key_missing"

    params = {
        "q": build_query(display_name, language, GNEWS),
        "max": max(1, min(max_articles, 10)),
        "sortby": "publishedAt",
        "apikey": api_key,
        **GNEWS_LOCALES[language],
    }

    attempts = len(GNEWS_RETRY_BACKOFF_SECONDS) + 1
    last_error = "gnews_unreachable"
    for attempt in range(attempts):
        if throttle is not None:
            await throttle.wait()
        try:
            response = await client.get(
                f"{settings.gnews_base_url}/search", params=params
            )
        except httpx.HTTPError as error:
            last_error = f"transport_error {type(error).__name__}: {redact(str(error))}"
        else:
            if response.status_code == 200:
                try:
                    payload = response.json()
                except ValueError:
                    return [], f"unreadable_response: {redact(response.text)}"
                return parse_gnews(payload, language), None
            last_error = (
                f"http_{response.status_code}: {redact(response.text)}"
            )
            if response.status_code != 429:
                return [], last_error

        if attempt < len(GNEWS_RETRY_BACKOFF_SECONDS):
            await asyncio.sleep(GNEWS_RETRY_BACKOFF_SECONDS[attempt])

    return [], f"{last_error} (gave up after {attempts} attempts)"


def merge_sources(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for group in groups:
        for article in group:
            key = article["dedupeKey"]
            current = best.get(key)
            if current is None:
                best[key] = dict(article)
                best[key]["alsoFoundBy"] = []
                continue
            if article["sourceApi"] not in current["alsoFoundBy"] and (
                article["sourceApi"] != current["sourceApi"]
            ):
                current["alsoFoundBy"].append(article["sourceApi"])
            if not current["description"] and article["description"]:
                carried = current["alsoFoundBy"] + [current["sourceApi"]]
                replacement = dict(article)
                replacement["alsoFoundBy"] = [
                    api for api in carried if api != article["sourceApi"]
                ]
                best[key] = replacement
    return list(best.values())
