import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from backend.vendors import news_watcher
from backend.vendors.news_sources import (
    GNEWS,
    GNEWS_QUERY_MAX_CHARS,
    GOOGLE_NEWS,
    build_query,
    dedupe_key,
    merge_sources,
    normalise_title,
    normalise_url,
    parse_gnews,
    parse_google_news,
)
from backend.vendors.news_watcher import (
    WatcherConfig,
    matched_keywords,
    parse_classification,
    run,
)

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item>
  <title>Netflix scumpeste abonamentul in Romania cu 20%</title>
  <link>https://example.test/a</link>
  <guid>guid-a</guid>
  <pubDate>Tue, 04 Aug 2026 09:30:00 GMT</pubDate>
  <source url="https://x.test">Ziarul X</source>
</item>
<item>
  <title>Netflix anunta un nou serial documentar</title>
  <link>https://example.test/b</link>
  <guid>guid-b</guid>
  <pubDate>Wed, 05 Aug 2026 11:00:00 GMT</pubDate>
  <source url="https://y.test">Ziarul Y</source>
</item>
</channel></rss>"""


class FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        return list(self._docs)


class FakeCollection:
    def __init__(self, docs: list[dict[str, Any]] | None = None) -> None:
        self.docs = docs or []
        self.written: list[Any] = []

    async def create_index(self, *args: Any, **kwargs: Any) -> None:
        return None

    def find(self, query: dict[str, Any], projection: Any = None) -> FakeCursor:
        matched = [
            doc
            for doc in self.docs
            if all(doc.get(key) == value for key, value in query.items())
        ]
        return FakeCursor(matched)

    async def bulk_write(self, operations: list[Any], ordered: bool = True) -> None:
        self.written.extend(operations)


class FakeDb:
    def __init__(self, collections: dict[str, FakeCollection]) -> None:
        self._collections = collections

    def __getitem__(self, name: str) -> FakeCollection:
        return self._collections.setdefault(name, FakeCollection())


def netflix_stats() -> list[dict[str, Any]]:
    return [
        {
            "source": "unit",
            "vendorNormalized": "NETFLIX",
            "currency": "RON",
            "counterpartyVariants": ["Netflix"],
            "categories": ["entertainment"],
        }
    ]


def article(
    key: str = "k1",
    title: str = "Netflix scumpeste abonamentul",
    description: str = "",
    api: str = GOOGLE_NEWS,
) -> dict[str, Any]:
    return {
        "title": title,
        "description": description,
        "url": f"https://example.test/{key}",
        "publishedAt": datetime(2026, 8, 4, tzinfo=UTC),
        "publisher": "Ziarul X",
        "publisherCountry": "ro",
        "language": "ro",
        "sourceApi": api,
        "dedupeKey": key,
        "alsoFoundBy": [],
    }


def drive(
    monkeypatch: pytest.MonkeyPatch,
    articles: list[dict[str, Any]],
    seen: list[dict[str, Any]],
    verdict: tuple[dict[str, Any] | None, str | None] = (
        {
            "confirms_increase": True,
            "percent_increase": 20.0,
            "effective_date": "2026-09-01",
            "market": "RO",
            "confidence": "high",
            "summary": "Serviciul isi majoreaza tariful lunar.",
        },
        None,
    ),
    config: WatcherConfig | None = None,
) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    calls: list[str] = []
    prompts: list[dict[str, Any]] = []

    async def fake_google(client: Any, display_name: str, language: str) -> list[dict[str, Any]]:
        return [row for row in articles if row["sourceApi"] == GOOGLE_NEWS] if language == "ro" else []

    async def fake_gnews(
        client: Any,
        display_name: str,
        language: str,
        max_articles: int,
        throttle: Any = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        if language != "ro":
            return [], None
        return [row for row in articles if row["sourceApi"] == GNEWS], None

    async def fake_classify(
        client: Any, display_name: str, item: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None]:
        calls.append(item["dedupeKey"])
        prompts.append(item)
        return verdict

    monkeypatch.setattr(news_watcher, "fetch_google_news", fake_google)
    monkeypatch.setattr(news_watcher, "fetch_gnews", fake_gnews)
    monkeypatch.setattr(news_watcher, "classify", fake_classify)

    db = FakeDb(
        {
            "vendorMonthlyStats": FakeCollection(netflix_stats()),
            "newsArticlesSeen": FakeCollection(seen),
            "newsSignals": FakeCollection(),
        }
    )
    outcome = asyncio.run(
        run(db, config or WatcherConfig(source_collection="unit", apis=(GOOGLE_NEWS,)))
    )
    return outcome, calls, prompts


def test_the_feed_parser_reads_title_link_date_and_publisher() -> None:
    articles = parse_google_news(RSS, "ro")

    assert len(articles) == 2
    assert articles[0]["url"] == "https://example.test/a"
    assert articles[0]["publisher"] == "Ziarul X"
    assert articles[0]["publishedAt"] == datetime(2026, 8, 4, 9, 30, tzinfo=UTC)
    assert articles[0]["description"] == ""


def test_a_broken_feed_yields_nothing_instead_of_raising() -> None:
    assert parse_google_news("<rss><channel><item>", "ro") == []
    assert parse_google_news("", "ro") == []


def test_the_keyword_filter_keeps_price_talk_and_drops_the_rest() -> None:
    assert matched_keywords("Netflix scumpește abonamentul în România")
    assert matched_keywords("Netflix raises prices again")
    assert matched_keywords("Enel majorare tarif energie")
    assert matched_keywords("Digi anunță prețuri noi") == ["pret"]

    assert matched_keywords("Netflix anunță un nou serial documentar") == []
    assert matched_keywords("Enel a semnat un parteneriat eolian") == []


def test_an_article_the_keyword_filter_rejects_never_reaches_the_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boring = article("k-boring", "Netflix anunta un nou serial documentar")

    outcome, calls, _prompts = drive(monkeypatch, [boring], seen=[])

    assert calls == []
    assert outcome["llm_calls_used"] == 0
    assert outcome["stats"]["NETFLIX"]["keyword_rejected"] == 1
    assert outcome["signals"] == []


def test_an_article_already_on_record_is_not_classified_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    known = article("k-seen")
    seen = [{"vendorNormalized": "NETFLIX", "articleKey": "k-seen"}]

    outcome, calls, _prompts = drive(monkeypatch, [known], seen=seen)

    assert calls == []
    assert outcome["llm_calls_used"] == 0
    assert outcome["stats"]["NETFLIX"]["already_seen"] == 1


def test_a_fresh_article_is_classified_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcome, calls, _prompts = drive(monkeypatch, [article("k-new")], seen=[])

    assert calls == ["k-new"]
    assert outcome["stats"]["NETFLIX"]["confirmed"] == 1
    assert outcome["signals"][0]["percentIncrease"] == 20.0
    assert outcome["signals"][0]["source"] == "google_news"


def test_the_call_budget_caps_spending_even_with_many_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    many = [article(f"k{index}") for index in range(10)]
    config = WatcherConfig(source_collection="unit", max_llm_calls=3)

    outcome, calls, _prompts = drive(monkeypatch, many, seen=[], config=config)

    assert len(calls) == 3
    assert outcome["llm_calls_used"] == 3
    assert outcome["stats"]["NETFLIX"]["budget_skipped"] == 7


def test_a_dry_run_spends_nothing_and_records_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = WatcherConfig(source_collection="unit", dry_run=True)

    outcome, calls, _prompts = drive(monkeypatch, [article("k-dry")], seen=[], config=config)

    assert calls == []
    assert outcome["llm_calls_used"] == 0
    assert outcome["signals"] == []


def test_a_well_formed_verdict_is_read_into_typed_fields() -> None:
    parsed = parse_classification(
        '{"confirms_increase": true, "percent_increase": 12.5, '
        '"effective_date": "2026-09-01", "market": "RO", '
        '"confidence": "high", "summary": "Tariful lunar creste."}'
    )

    assert parsed is not None
    assert parsed["confirms_increase"] is True
    assert parsed["percent_increase"] == 12.5
    assert parsed["confidence"] == "high"


def test_a_verdict_wrapped_in_a_code_fence_is_still_read() -> None:
    parsed = parse_classification(
        '```json\n{"confirms_increase": false, "confidence": "low"}\n```'
    )

    assert parsed is not None
    assert parsed["confirms_increase"] is False


def test_malformed_model_output_is_rejected_without_raising() -> None:
    for raw in (
        "",
        "not json at all",
        "{",
        '{"confirms_increase": "yes"}',
        '{"percent_increase": 10}',
        "[1, 2, 3]",
        '{"confirms_increase": true, "percent_increase": "twenty"}',
    ):
        result = parse_classification(raw)
        assert result is None or result["percent_increase"] is None


def test_an_unusable_verdict_does_not_stop_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcome, calls, _prompts = drive(
        monkeypatch, [article("k-bad")], seen=[], verdict=(None, "malformed_json")
    )

    assert calls == ["k-bad"]
    assert outcome["signals"] == []
    assert outcome["stats"]["NETFLIX"]["llm_failed"] == 1
    assert outcome["failures"] == [{"vendor": "NETFLIX", "reason": "malformed_json"}]


def test_a_nonsense_confidence_value_falls_back_to_low() -> None:
    parsed = parse_classification(
        '{"confirms_increase": true, "confidence": "extremely sure"}'
    )

    assert parsed is not None
    assert parsed["confidence"] == "low"


def test_the_article_key_is_stable_across_runs() -> None:
    title = "Netflix scumpeste abonamentul in Romania"
    assert dedupe_key(title, "https://x.test/a") == dedupe_key(title, "https://x.test/b")
    assert dedupe_key(title, "https://x.test/a") != dedupe_key(
        "Enel majoreaza tariful la energie", "https://x.test/a"
    )


def test_the_queries_carry_the_display_name_in_both_languages() -> None:
    assert "Enel Energie" in build_query("Enel Energie", "ro")
    assert "Enel Energie" in build_query("Enel Energie", "en")
    assert build_query("Netflix", "ro") != build_query("Netflix", "en")


GNEWS_PAYLOAD = {
    "totalArticles": 2,
    "articles": [
        {
            "id": "gn-1",
            "title": "Netflix scumpeste abonamentul in Romania",
            "description": "Netflix majoreaza tariful standard cu 20%, de la 49 la 59 lei, incepand cu 1 septembrie 2026.",
            "content": "truncated...",
            "url": "https://ziar.ro/netflix-scump?utm_source=rss&oc=5",
            "publishedAt": "2026-08-04T09:30:00Z",
            "lang": "ro",
            "source": {"name": "Ziarul X", "url": "https://ziar.ro", "country": "ro"},
        },
        {
            "id": "gn-2",
            "title": "Netflix lanseaza un serial nou",
            "description": "Productia va fi disponibila din toamna.",
            "url": "https://ziar.ro/netflix-serial",
            "publishedAt": "2026-08-05T11:00:00Z",
            "lang": "ro",
            "source": {"name": "Ziarul Y", "country": "ro"},
        },
    ],
}


def test_the_gnews_parser_keeps_the_description_and_country() -> None:
    articles = parse_gnews(GNEWS_PAYLOAD, "ro")

    assert len(articles) == 2
    assert articles[0]["description"].startswith("Netflix majoreaza tariful")
    assert articles[0]["publisherCountry"] == "ro"
    assert articles[0]["sourceApi"] == GNEWS
    assert articles[0]["publishedAt"] == datetime(2026, 8, 4, 9, 30, tzinfo=UTC)


def test_a_gnews_payload_without_articles_is_not_a_crash() -> None:
    assert parse_gnews({}, "ro") == []
    assert parse_gnews({"articles": None}, "ro") == []
    assert parse_gnews({"articles": ["nonsense", {}]}, "ro") == []


def test_tracking_parameters_do_not_make_two_urls_look_different() -> None:
    assert normalise_url("https://www.ziar.ro/a/?utm_source=rss&id=7") == normalise_url(
        "https://ziar.ro/a?id=7"
    )
    assert normalise_url("https://ziar.ro/a") != normalise_url("https://ziar.ro/b")


def test_the_publisher_suffix_google_appends_does_not_break_matching() -> None:
    google_title = "Netflix scumpește abonamentul în România - Wall-Street.ro"
    gnews_title = "Netflix scumpeste abonamentul in Romania"

    assert normalise_title(google_title) == normalise_title(gnews_title)


def test_the_same_story_from_both_sources_is_merged_and_keeps_the_description() -> None:
    story = "Netflix scumpeste abonamentul in Romania"
    from_google = parse_google_news(
        f"""<?xml version="1.0"?><rss><channel><item>
        <title>{story} - Wall-Street.ro</title>
        <link>https://news.google.com/rss/articles/CBMiABC</link>
        <pubDate>Tue, 04 Aug 2026 09:30:00 GMT</pubDate>
        <source url="https://ws.ro">Wall-Street.ro</source>
        </item></channel></rss>""",
        "ro",
    )
    from_gnews = parse_gnews(GNEWS_PAYLOAD, "ro")

    merged = merge_sources(from_gnews, from_google)

    assert len(merged) == 2
    netflix = [row for row in merged if normalise_title(row["title"]) == normalise_title(story)]
    assert len(netflix) == 1
    assert netflix[0]["sourceApi"] == GNEWS
    assert netflix[0]["description"] != ""
    assert GOOGLE_NEWS in netflix[0]["alsoFoundBy"]


def test_a_cross_source_duplicate_is_classified_only_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shared = "k-shared"
    both = [
        article(shared, description="Tariful creste cu 20% din septembrie.", api=GNEWS),
        article(shared, api=GOOGLE_NEWS),
    ]
    config = WatcherConfig(source_collection="unit", apis=(GNEWS, GOOGLE_NEWS))

    outcome, calls, prompts = drive(monkeypatch, both, seen=[], config=config)

    assert calls == [shared]
    assert outcome["llm_calls_used"] == 1
    assert prompts[0]["description"] != ""


def test_the_keyword_filter_now_reads_the_description_too() -> None:
    title = "Netflix anunta noutati pentru abonati in Romania"
    description = "Tariful lunar va creste de la 49 la 59 de lei."

    assert matched_keywords(title) == []
    assert "creste" in matched_keywords(title, description)
    assert "tarif" in matched_keywords(title, description)


def test_a_headline_only_article_can_still_be_rejected_on_both_fields() -> None:
    assert matched_keywords("Netflix a semnat un regizor", "Filmarile incep in toamna") == []


def test_the_description_reaches_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    rich = article(
        "k-rich",
        description="Tariful standard creste cu 20%, de la 49 la 59 lei, din 1 septembrie 2026.",
        api=GNEWS,
    )
    config = WatcherConfig(source_collection="unit", apis=(GNEWS,))

    _outcome, calls, prompts = drive(monkeypatch, [rich], seen=[], config=config)

    assert calls == ["k-rich"]
    assert "59 lei" in prompts[0]["description"]
    assert prompts[0]["publisherCountry"] == "ro"


def test_a_dry_run_still_writes_nothing_with_two_sources_wired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_before: list[dict[str, Any]] = []
    config = WatcherConfig(
        source_collection="unit", apis=(GNEWS, GOOGLE_NEWS), dry_run=True
    )

    outcome, calls, _prompts = drive(
        monkeypatch,
        [
            article("k-a", description="Tariful creste cu 20%.", api=GNEWS),
            article("k-b", api=GOOGLE_NEWS),
        ],
        seen=seen_before,
        config=config,
    )

    assert calls == []
    assert outcome["llm_calls_used"] == 0
    assert outcome["signals"] == []
    assert seen_before == []


def test_only_the_gnews_query_uses_boolean_syntax() -> None:
    rss_ro = build_query("Netflix", "ro")
    rss_en = build_query("Netflix", "en")

    assert "AND" not in rss_ro and "OR" not in rss_ro
    assert rss_ro == "Netflix scumpire pret abonament"
    assert rss_en == "Netflix price increase subscription"

    gnews_ro = build_query("Netflix", "ro", GNEWS)
    gnews_en = build_query("Netflix", "en", GNEWS)

    assert gnews_ro.startswith('"Netflix" AND (')
    assert " OR " in gnews_ro
    assert "scumpire" in gnews_ro and "tarif" in gnews_ro
    assert " OR " in gnews_en
    assert "subscription" in gnews_en


def test_the_gnews_query_stays_inside_the_length_cap_and_stays_balanced() -> None:
    for vendor in ("Netflix", "Digi Communications", "X" * 400):
        for language in ("ro", "en"):
            query = build_query(vendor, language, GNEWS)

            assert len(query) <= GNEWS_QUERY_MAX_CHARS
            assert query.count("(") == query.count(")")
            assert query.count('"') % 2 == 0
            assert query.endswith(")")


def test_a_vendor_name_cannot_break_out_of_the_quoted_term() -> None:
    query = build_query('Net"flix" OR anything', "en", GNEWS)

    assert query.count('"') == 2
    assert query.startswith('"Netflix OR anything" AND (')
