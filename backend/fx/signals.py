from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.fx.bnr_feed import SOURCE, SOURCE_NAME, SOURCE_PAGE_URL
from backend.fx.validation import (
    BASE_CURRENCY,
    convert_minor,
    percent_change,
    percent_text,
)

RATES_COLLECTION = "fxRatesDaily"
SIGNALS_COLLECTION = "fxSignals"
NOTIFICATIONS_COLLECTION = "fxNotifications"

RATE_UNIQUE_KEY = ("source", "currency", "date")
SIGNAL_UNIQUE_KEY = ("source", "currency", "date")
NOTIFICATION_UNIQUE_KEY = ("source", "userId", "currency", "signalDate")

UP = "up"
DOWN = "down"
PENDING = "pending"

NO_BASELINE = "no_baseline_in_window"
BELOW_THRESHOLD = "below_threshold"
NO_HOLDER = "no_holder_in_that_currency"
BELOW_MIN_BALANCE = "balance_below_minimum"
SAME_RATE_STATE = "same_rate_state_already_notified"

AMOUNT_SLOT = "{amount}"
RON_SLOT = "{ron}"
RON_BEFORE_SLOT = "{ronBefore}"

VERB_BY_DIRECTION = {UP: "a crescut cu", DOWN: "a scăzut cu"}
VERB_BY_DIRECTION_EN = {UP: "rose", DOWN: "fell"}

SHORT_TEMPLATE = "{currency} {sign}{percent}% în {days} zile"
SHORT_TEMPLATE_EN = "{currency} {sign}{percent}% in {days} days"

LONG_TEMPLATE = (
    "{currency} {verb} {percent}% în {days} zile — "
    "soldul tău de {amount} valorează acum {ron}, față de {ronBefore}."
)
LONG_TEMPLATE_EN = (
    "{currency} {verb} {percent}% in {days} days — "
    "your {amount} is now worth {ron}, vs {ronBefore} before."
)

SHORT_TEXT_LIMIT = 60


class SignalRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str = SOURCE
    source_name: str = SOURCE_NAME
    source_url: str = SOURCE_PAGE_URL
    baseline_days: int = 7
    threshold_percent: float = 1.5
    repeat_rate_tolerance_percent: float = 0.5
    min_balance_minor_units: int = 1
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def rate_record(
    currency: str, day: str, rate_micro: int, multiplier: int, source: str
) -> dict[str, Any]:
    return {
        "source": source,
        "currency": currency,
        "date": day,
        "baseCurrency": BASE_CURRENCY,
        "rateMicroUnits": rate_micro,
        "multiplier": multiplier,
    }


def resolve_baseline(
    history: dict[str, int], current_date: str, baseline_days: int
) -> tuple[str, int] | None:
    cutoff = (date.fromisoformat(current_date) - timedelta(days=baseline_days)).isoformat()
    candidates = [day for day in history if day <= cutoff]
    if not candidates:
        return None
    chosen = max(candidates)
    return chosen, history[chosen]


def direction_of(change_percent: float) -> str:
    return UP if change_percent > 0 else DOWN


def build_signal(
    currency: str,
    current_date: str,
    current_rate_micro: int,
    history: dict[str, int],
    rule: SignalRule,
) -> tuple[dict[str, Any] | None, str]:
    resolved = resolve_baseline(history, current_date, rule.baseline_days)
    if resolved is None:
        return None, NO_BASELINE

    baseline_date, baseline_rate_micro = resolved
    change = percent_change(current_rate_micro, baseline_rate_micro)
    if abs(change) < rule.threshold_percent:
        return None, BELOW_THRESHOLD

    return {
        "source": rule.source,
        "currency": currency,
        "date": current_date,
        "changePercent": round(change, 4),
        "direction": direction_of(change),
        "baselineRate": baseline_rate_micro,
        "currentRate": current_rate_micro,
        "baseCurrency": BASE_CURRENCY,
        "baselineDate": baseline_date,
        "baselineDays": rule.baseline_days,
        "thresholdPercent": rule.threshold_percent,
        "signalKey": f"{rule.source}:{currency}:{current_date}",
        "foundAt": rule.generated_at,
    }, ""


def sign_of(change_percent: float) -> str:
    return "+" if change_percent > 0 else "−"


def clip(text: str) -> str:
    if len(text) <= SHORT_TEXT_LIMIT:
        return text
    return text[: SHORT_TEXT_LIMIT - 1] + "…"


def render_short(signal: dict[str, Any]) -> str:
    return clip(
        SHORT_TEMPLATE.format(
            currency=signal["currency"],
            sign=sign_of(signal["changePercent"]),
            percent=percent_text(signal["changePercent"], ","),
            days=signal["baselineDays"],
        )
    )


def render_short_en(signal: dict[str, Any]) -> str:
    return clip(
        SHORT_TEMPLATE_EN.format(
            currency=signal["currency"],
            sign=sign_of(signal["changePercent"]),
            percent=percent_text(signal["changePercent"], "."),
            days=signal["baselineDays"],
        )
    )


def render_long(signal: dict[str, Any]) -> str:
    return LONG_TEMPLATE.format(
        amount=AMOUNT_SLOT,
        ron=RON_SLOT,
        ronBefore=RON_BEFORE_SLOT,
        currency=signal["currency"],
        verb=VERB_BY_DIRECTION[signal["direction"]],
        percent=percent_text(signal["changePercent"], ","),
        days=signal["baselineDays"],
    )


def render_long_en(signal: dict[str, Any]) -> str:
    return LONG_TEMPLATE_EN.format(
        amount=AMOUNT_SLOT,
        ron=RON_SLOT,
        ronBefore=RON_BEFORE_SLOT,
        currency=signal["currency"],
        verb=VERB_BY_DIRECTION_EN[signal["direction"]],
        percent=percent_text(signal["changePercent"], "."),
        days=signal["baselineDays"],
    )


def repeats_notified_rate(
    previous: dict[str, Any], current_rate_micro: int, tolerance_percent: float
) -> bool:
    known = previous.get("currentRate")
    if not isinstance(known, int) or known <= 0:
        return False
    return abs(percent_change(current_rate_micro, known)) <= tolerance_percent


def render_notification(
    signal: dict[str, Any], holding: dict[str, Any], rule: SignalRule
) -> dict[str, Any]:
    return {
        "source": signal["source"],
        "userId": holding["userId"],
        "currency": signal["currency"],
        "signalDate": signal["date"],
        "signalKey": signal["signalKey"],
        "direction": signal["direction"],
        "changePercent": signal["changePercent"],
        "baselineRate": signal["baselineRate"],
        "currentRate": signal["currentRate"],
        "baselineDate": signal["baselineDate"],
        "baselineDays": signal["baselineDays"],
        "amountMinorUnits": holding["amountMinorUnits"],
        "ronEquivalentMinorUnits": convert_minor(
            holding["amountMinorUnits"], signal["currentRate"]
        ),
        "ronBaselineMinorUnits": convert_minor(
            holding["amountMinorUnits"], signal["baselineRate"]
        ),
        "ronCurrency": signal["baseCurrency"],
        "sourceName": rule.source_name,
        "sourceUrl": rule.source_url,
        "shortText": render_short(signal),
        "longText": render_long(signal),
        "shortTextEn": render_short_en(signal),
        "longTextEn": render_long_en(signal),
        "status": PENDING,
        "createdAt": rule.generated_at,
    }


def build_notifications(
    signals: list[dict[str, Any]],
    holdings: list[dict[str, Any]],
    already_notified: dict[tuple[str, str], dict[str, Any]],
    rule: SignalRule,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_currency: dict[str, list[dict[str, Any]]] = {}
    for holding in holdings:
        by_currency.setdefault(holding["currency"], []).append(holding)

    notifications: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for signal in sorted(signals, key=lambda row: (row["currency"], row["date"])):
        holders = sorted(
            by_currency.get(signal["currency"], []), key=lambda row: row["userId"]
        )
        if not holders:
            skipped.append(
                {
                    "currency": signal["currency"],
                    "signalDate": signal["date"],
                    "userId": None,
                    "reason": NO_HOLDER,
                }
            )
            continue

        for holding in holders:
            if holding["amountMinorUnits"] < rule.min_balance_minor_units:
                skipped.append(
                    {
                        "currency": signal["currency"],
                        "signalDate": signal["date"],
                        "userId": holding["userId"],
                        "reason": BELOW_MIN_BALANCE,
                        "amountMinorUnits": holding["amountMinorUnits"],
                    }
                )
                continue

            previous = already_notified.get((holding["userId"], signal["currency"]))
            if (
                previous is not None
                and previous.get("signalDate") != signal["date"]
                and repeats_notified_rate(
                    previous, signal["currentRate"], rule.repeat_rate_tolerance_percent
                )
            ):
                skipped.append(
                    {
                        "currency": signal["currency"],
                        "signalDate": signal["date"],
                        "userId": holding["userId"],
                        "reason": SAME_RATE_STATE,
                        "notifiedSignalDate": previous.get("signalDate"),
                        "notifiedRate": previous.get("currentRate"),
                        "currentRate": signal["currentRate"],
                    }
                )
                continue

            notifications.append(render_notification(signal, holding, rule))

    return notifications, skipped
