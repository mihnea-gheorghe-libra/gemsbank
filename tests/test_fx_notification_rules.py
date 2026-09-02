from typing import Any

from backend.fx.signals import (
    BELOW_MIN_BALANCE,
    NO_HOLDER,
    NOTIFICATION_UNIQUE_KEY,
    PENDING,
    SAME_RATE_STATE,
    SignalRule,
    build_notifications,
    build_signal,
    render_long,
    render_long_en,
    repeats_notified_rate,
)

RULE = SignalRule()

EUR_HISTORY = {"2026-08-19": 5_180_000}
USD_HISTORY = {"2026-08-19": 4_400_100}

GABRIELA = "01a01ed4-99bc-728d-8a58-a239b290a161"
MARIA = "01a01f08-343e-79d8-b22e-a30d1ad2e358"


def eur_signal(day: str = "2026-08-26", rate: int = 5_258_900) -> dict[str, Any]:
    signal, _ = build_signal("EUR", day, rate, EUR_HISTORY, RULE)
    assert signal is not None
    return signal


def usd_signal(day: str = "2026-08-26", rate: int = 4_507_700) -> dict[str, Any]:
    signal, _ = build_signal("USD", day, rate, USD_HISTORY, RULE)
    assert signal is not None
    return signal


def holding(user_id: str, currency: str, minor: int) -> dict[str, Any]:
    return {
        "userId": user_id,
        "currency": currency,
        "amountMinorUnits": minor,
        "accountIds": ["acc-1"],
    }


def test_only_a_holder_of_that_currency_is_told_about_its_rate() -> None:
    holdings = [holding(GABRIELA, "EUR", 150_00), holding(MARIA, "USD", 200_00)]

    notifications, _ = build_notifications([eur_signal()], holdings, {}, RULE)

    assert [row["userId"] for row in notifications] == [GABRIELA]
    assert notifications[0]["currency"] == "EUR"


def test_a_zero_balance_in_that_currency_earns_no_notification() -> None:
    holdings = [holding(GABRIELA, "EUR", 0), holding(MARIA, "EUR", 1)]

    notifications, skipped = build_notifications([eur_signal()], holdings, {}, RULE)

    assert [row["userId"] for row in notifications] == [MARIA]
    assert [row["reason"] for row in skipped] == [BELOW_MIN_BALANCE]
    assert skipped[0]["userId"] == GABRIELA


def test_a_signal_nobody_is_exposed_to_is_recorded_but_notifies_no_one() -> None:
    notifications, skipped = build_notifications(
        [eur_signal()], [holding(MARIA, "USD", 200_00)], {}, RULE
    )

    assert notifications == []
    assert [row["reason"] for row in skipped] == [NO_HOLDER]


def test_every_holder_of_the_currency_is_told_once_each() -> None:
    holdings = [holding(GABRIELA, "EUR", 150_00), holding(MARIA, "EUR", 900_00)]

    notifications, _ = build_notifications([eur_signal()], holdings, {}, RULE)

    assert sorted(row["userId"] for row in notifications) == sorted([GABRIELA, MARIA])


def test_two_currencies_that_both_moved_produce_two_separate_notifications() -> None:
    holdings = [holding(GABRIELA, "EUR", 150_00), holding(GABRIELA, "USD", 300_00)]

    notifications, _ = build_notifications(
        [eur_signal(), usd_signal()], holdings, {}, RULE
    )

    assert [row["currency"] for row in notifications] == ["EUR", "USD"]


def test_the_notification_carries_the_holders_own_amount_and_its_ron_worth() -> None:
    notifications, _ = build_notifications(
        [eur_signal()], [holding(GABRIELA, "EUR", 150_00)], {}, RULE
    )

    row = notifications[0]
    assert row["amountMinorUnits"] == 15000
    assert row["ronEquivalentMinorUnits"] == 78884
    assert row["ronCurrency"] == "RON"
    assert row["status"] == PENDING


def test_the_notification_says_what_the_same_amount_was_worth_before() -> None:
    notifications, _ = build_notifications(
        [eur_signal()], [holding(GABRIELA, "EUR", 150_00)], {}, RULE
    )

    row = notifications[0]
    assert row["ronBaselineMinorUnits"] == 77700
    assert row["ronEquivalentMinorUnits"] > row["ronBaselineMinorUnits"]


def test_a_fall_makes_the_before_value_the_larger_of_the_two() -> None:
    signal, _ = build_signal("EUR", "2026-08-26", 5_000_000, {"2026-08-19": 5_180_000}, RULE)
    assert signal is not None

    notifications, _ = build_notifications(
        [signal], [holding(GABRIELA, "EUR", 150_00)], {}, RULE
    )

    row = notifications[0]
    assert row["ronBaselineMinorUnits"] == 77700
    assert row["ronEquivalentMinorUnits"] == 75000


def test_money_travels_as_slots_the_frontend_formats_never_as_baked_in_text() -> None:
    notifications, _ = build_notifications(
        [eur_signal()], [holding(GABRIELA, "EUR", 150_00)], {}, RULE
    )

    row = notifications[0]
    for text in (row["longText"], row["longTextEn"]):
        assert "{amount}" in text
        assert "{ron}" in text
        assert "{ronBefore}" in text
    assert "150" not in row["longText"]
    assert "777" not in row["longText"]


def test_the_text_is_built_from_the_signal_not_hardcoded_per_currency() -> None:
    eur = render_long(eur_signal())
    usd = render_long(usd_signal())

    assert eur.startswith("EUR ")
    assert usd.startswith("USD ")
    assert eur.replace("EUR", "X") != usd.replace("USD", "X")
    assert "a crescut cu" in eur
    assert "rose" in render_long_en(eur_signal())


def test_the_long_text_stays_one_short_sentence() -> None:
    for text in (render_long(eur_signal()), render_long_en(eur_signal())):
        assert len(text) <= 105
        assert text.endswith(".")
        assert ". " not in text


def test_the_before_slot_is_not_eaten_by_the_now_slot() -> None:
    for text in (render_long(eur_signal()), render_long_en(eur_signal())):
        assert text.count("{ron}") == 1
        assert text.count("{ronBefore}") == 1


def test_the_raw_rates_stay_in_the_data_and_out_of_the_sentence() -> None:
    text = render_long(eur_signal())

    assert "5,2589" not in text
    assert "5,2452" not in text
    assert eur_signal()["currentRate"] == 5_258_900


def test_a_fall_is_worded_as_a_fall_in_both_languages() -> None:
    signal, _ = build_signal("EUR", "2026-08-26", 5_000_000, {"2026-08-19": 5_180_000}, RULE)
    assert signal is not None

    assert "a scăzut cu" in render_long(signal)
    assert "fell" in render_long_en(signal)


def test_a_percentage_reads_with_a_comma_in_romanian_and_a_dot_in_english() -> None:
    signal = eur_signal()

    assert "1,5%" in render_long(signal)
    assert "1.5%" in render_long_en(signal)


def test_every_notification_carries_a_clickable_source_for_the_frontend() -> None:
    notifications, _ = build_notifications(
        [eur_signal()], [holding(GABRIELA, "EUR", 150_00)], {}, RULE
    )

    row = notifications[0]
    assert row["sourceName"] == "Banca Națională a României"
    assert row["sourceUrl"].startswith("https://www.bnr.ro/")


def test_the_source_url_is_configurable_without_touching_the_templates() -> None:
    rule = SignalRule(source_url="https://example.test/rates", source_name="Elsewhere")

    notifications, _ = build_notifications(
        [eur_signal()], [holding(GABRIELA, "EUR", 150_00)], {}, rule
    )

    assert notifications[0]["sourceUrl"] == "https://example.test/rates"
    assert notifications[0]["sourceName"] == "Elsewhere"


def test_the_dedupe_key_makes_a_rerun_replay_the_same_document() -> None:
    holdings = [holding(GABRIELA, "EUR", 150_00)]

    first, _ = build_notifications([eur_signal()], holdings, {}, RULE)
    already = {(GABRIELA, "EUR"): first[0]}
    second, skipped = build_notifications([eur_signal()], holdings, already, RULE)

    assert NOTIFICATION_UNIQUE_KEY == ("source", "userId", "currency", "signalDate")
    assert {field: first[0][field] for field in NOTIFICATION_UNIQUE_KEY} == {
        field: second[0][field] for field in NOTIFICATION_UNIQUE_KEY
    }
    assert first[0]["longText"] == second[0]["longText"]
    assert skipped == []


def test_the_same_rate_seen_again_on_a_later_day_does_not_notify_twice() -> None:
    holdings = [holding(GABRIELA, "EUR", 150_00)]
    first, _ = build_notifications([eur_signal()], holdings, {}, RULE)
    already = {(GABRIELA, "EUR"): first[0]}

    later = eur_signal(day="2026-08-27", rate=5_260_000)
    notifications, skipped = build_notifications([later], holdings, already, RULE)

    assert notifications == []
    assert [row["reason"] for row in skipped] == [SAME_RATE_STATE]


def test_a_genuinely_new_move_does_notify_again() -> None:
    holdings = [holding(GABRIELA, "EUR", 150_00)]
    first, _ = build_notifications([eur_signal()], holdings, {}, RULE)
    already = {(GABRIELA, "EUR"): first[0]}

    later = eur_signal(day="2026-09-03", rate=5_400_000)
    notifications, skipped = build_notifications([later], holdings, already, RULE)

    assert [row["signalDate"] for row in notifications] == ["2026-09-03"]
    assert skipped == []


def test_the_repeat_guard_is_a_tolerance_not_an_equality_test() -> None:
    previous = {"currentRate": 5_258_900}

    assert repeats_notified_rate(previous, 5_260_000, 0.5) is True
    assert repeats_notified_rate(previous, 5_400_000, 0.5) is False
    assert repeats_notified_rate({}, 5_260_000, 0.5) is False
