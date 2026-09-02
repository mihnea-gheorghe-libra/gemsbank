import pytest

from backend.fx.bnr_feed import parse_feed
from backend.fx.validation import rate_text, to_rate_micro

DAILY = """<?xml version="1.0" encoding="utf-8"?>
<DataSet xmlns="https://www.bnr.ro/xsd">
  <Header>
    <Publisher>National Bank of Romania</Publisher>
    <PublishingDate>2026-08-26</PublishingDate>
    <MessageType>DR</MessageType>
  </Header>
  <Body>
    <Subject>Reference rates</Subject>
    <OrigCurrency>RON</OrigCurrency>
    <Cube date="2026-08-26">
      <Rate currency="EUR">5.2589</Rate>
      <Rate currency="USD">4.5077</Rate>
      <Rate currency="HUF" multiplier="100">1.4592</Rate>
    </Cube>
  </Body>
</DataSet>
"""

TEN_DAYS = """<?xml version="1.0" encoding="utf-8"?>
<DataSet xmlns="https://www.bnr.ro/xsd">
  <Header>
    <Publisher>National Bank of Romania</Publisher>
    <PublishingDate>2026-08-26</PublishingDate>
    <MessageType>DR</MessageType>
  </Header>
  <Body>
    <OrigCurrency>RON</OrigCurrency>
    <Cube date="2026-08-17">
      <Rate currency="EUR">5.1712</Rate>
      <Rate currency="USD">4.4001</Rate>
    </Cube>
    <Cube date="2026-08-26">
      <Rate currency="EUR">5.2589</Rate>
      <Rate currency="USD">4.5077</Rate>
    </Cube>
  </Body>
</DataSet>
"""


def test_the_namespaced_feed_is_read_without_declaring_the_namespace() -> None:
    feed = parse_feed(DAILY)

    assert feed.publisher == "National Bank of Romania"
    assert feed.publishing_date == "2026-08-26"
    assert feed.base_currency == "RON"
    assert feed.currencies() == ("EUR", "HUF", "USD")


def test_a_rate_keeps_the_four_decimals_the_feed_published() -> None:
    feed = parse_feed(DAILY)
    eur = next(rate for rate in feed.rates if rate.currency == "EUR")

    assert eur.rate_micro == 5_258_900
    assert rate_text(eur.rate_micro) == "5.2589"
    assert eur.published_value == "5.2589"


def test_a_multiplier_is_divided_out_so_every_stored_rate_is_per_one_unit() -> None:
    feed = parse_feed(DAILY)
    huf = next(rate for rate in feed.rates if rate.currency == "HUF")

    assert huf.multiplier == 100
    assert huf.rate_micro == 14_592
    assert rate_text(huf.rate_micro) == "0.0146"


def test_a_multi_day_feed_keeps_every_cube_date() -> None:
    feed = parse_feed(TEN_DAYS)

    assert feed.dates() == ("2026-08-17", "2026-08-26")
    assert feed.latest_date() == "2026-08-26"
    assert len(feed.on("2026-08-17")) == 2


def test_only_the_currencies_we_track_are_taken_out_of_the_feed() -> None:
    feed = parse_feed(DAILY)

    kept = feed.for_currencies(("EUR", "USD"))

    assert [rate.currency for rate in kept] == ["EUR", "USD"]


def test_the_html_a_moved_feed_url_now_serves_is_rejected_not_parsed() -> None:
    with pytest.raises(ValueError, match="not valid XML|DataSet root"):
        parse_feed("<!doctype html><html><head><title>BNR</title></head></html>")


def test_a_feed_without_a_cube_is_an_error_not_an_empty_run() -> None:
    with pytest.raises(ValueError, match="no Cube"):
        parse_feed(
            '<DataSet xmlns="https://www.bnr.ro/xsd"><Body>'
            "<OrigCurrency>RON</OrigCurrency></Body></DataSet>"
        )


def test_a_cube_without_a_date_is_an_error_not_a_silently_dated_row() -> None:
    with pytest.raises(ValueError, match="no date"):
        parse_feed(
            '<DataSet xmlns="https://www.bnr.ro/xsd"><Body><Cube>'
            '<Rate currency="EUR">5.2589</Rate></Cube></Body></DataSet>'
        )


def test_a_negative_or_unreadable_rate_never_reaches_the_database() -> None:
    with pytest.raises(ValueError):
        to_rate_micro("-1.0")
    with pytest.raises(ValueError):
        to_rate_micro("not a rate")
    with pytest.raises(ValueError):
        to_rate_micro("5.2589", multiplier=0)
