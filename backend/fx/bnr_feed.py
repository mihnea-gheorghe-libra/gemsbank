from __future__ import annotations

from xml.etree import ElementTree

import httpx
from pydantic import BaseModel, ConfigDict

from backend.fx.validation import (
    BASE_CURRENCY,
    normalise_feed_currency,
    to_rate_micro,
)

SOURCE = "bnr"
SOURCE_NAME = "Banca Națională a României"
SOURCE_PAGE_URL = "https://www.bnr.ro/23988-cursurile-pietei-valutare-in-format-xml"
DAILY_FEED_URL = "https://curs.bnr.ro/nbrfxrates.xml"
TEN_DAY_FEED_URL = "https://curs.bnr.ro/nbrfxrates10days.xml"

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

ROOT_TAG = "DataSet"


class DailyRate(BaseModel):
    model_config = ConfigDict(frozen=True)

    currency: str
    date: str
    rate_micro: int
    multiplier: int
    published_value: str


class Feed(BaseModel):
    model_config = ConfigDict(frozen=True)

    publisher: str
    publishing_date: str
    base_currency: str
    rates: tuple[DailyRate, ...]

    def dates(self) -> tuple[str, ...]:
        return tuple(sorted({rate.date for rate in self.rates}))

    def latest_date(self) -> str:
        return self.dates()[-1]

    def currencies(self) -> tuple[str, ...]:
        return tuple(sorted({rate.currency for rate in self.rates}))

    def for_currencies(self, currencies: tuple[str, ...]) -> tuple[DailyRate, ...]:
        wanted = {currency.upper() for currency in currencies}
        return tuple(
            sorted(
                (rate for rate in self.rates if rate.currency in wanted),
                key=lambda rate: (rate.date, rate.currency),
            )
        )

    def on(self, day: str) -> tuple[DailyRate, ...]:
        return tuple(rate for rate in self.rates if rate.date == day)


def _local(tag: object) -> str:
    return str(tag).rpartition("}")[2]


def _children(node: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    return [child for child in node if _local(child.tag) == name]


def _first(node: ElementTree.Element | None, name: str) -> ElementTree.Element | None:
    if node is None:
        return None
    found = _children(node, name)
    return found[0] if found else None


def _text(node: ElementTree.Element | None) -> str:
    return (node.text or "").strip() if node is not None else ""


def _multiplier(entry: ElementTree.Element) -> int:
    raw = entry.get("multiplier")
    if raw is None:
        return 1
    try:
        return int(str(raw).strip())
    except ValueError as error:
        raise ValueError(f"unreadable BNR multiplier {raw!r}") from error


def parse_feed(xml_text: str) -> Feed:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as error:
        raise ValueError(f"the BNR feed is not valid XML: {error}") from error

    if _local(root.tag) != ROOT_TAG:
        raise ValueError(f"expected a BNR {ROOT_TAG} root, got {_local(root.tag)!r}")

    header = _first(root, "Header")
    body = _first(root, "Body")
    if body is None:
        raise ValueError("the BNR feed carries no Body")

    cubes = _children(body, "Cube")
    if not cubes:
        raise ValueError("the BNR feed carries no Cube")

    rates: list[DailyRate] = []
    for cube in cubes:
        day = (cube.get("date") or "").strip()
        if not day:
            raise ValueError("a BNR Cube carries no date attribute")
        for entry in _children(cube, "Rate"):
            currency = normalise_feed_currency(entry.get("currency"))
            published = _text(entry)
            if currency is None or not published:
                continue
            multiplier = _multiplier(entry)
            rates.append(
                DailyRate(
                    currency=currency,
                    date=day,
                    rate_micro=to_rate_micro(published, multiplier),
                    multiplier=multiplier,
                    published_value=published,
                )
            )

    if not rates:
        raise ValueError("the BNR feed carries no usable Rate")

    return Feed(
        publisher=_text(_first(header, "Publisher")),
        publishing_date=_text(_first(header, "PublishingDate")),
        base_currency=_text(_first(body, "OrigCurrency")) or BASE_CURRENCY,
        rates=tuple(rates),
    )


async def fetch_feed(
    url: str, timeout_seconds: float = 15.0
) -> tuple[Feed | None, str | None]:
    try:
        async with httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": BROWSER_UA, "Accept": "application/xml,text/xml"},
        ) as client:
            response = await client.get(url)
    except httpx.HTTPError as error:
        return None, f"transport_error:{type(error).__name__}"

    if response.status_code != 200:
        return None, f"http_{response.status_code}"

    content_type = response.headers.get("content-type", "")
    if "xml" not in content_type.lower():
        return None, f"not_xml:{content_type or 'unknown'}"

    try:
        return parse_feed(response.text), None
    except ValueError as error:
        return None, f"malformed_feed:{error}"
