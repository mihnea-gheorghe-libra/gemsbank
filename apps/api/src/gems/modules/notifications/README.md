# `notifications` — README only in v0

**Status:** no code. Folder reserved.

## Purpose

Channels (push, email, in-app), templates, delivery, and per-user notification preferences.

## Future public port

`notifications.application`:

- `send(user_id, template, params, channel_preference)`
- `list_preferences(user_id)` / `set_preferences(user_id, prefs)`

## How it will actually be driven

**By the outbox (seam 5), not by direct calls.** `payments` does not call `notifications` when a
transfer settles — it emits `PaymentSettled` to the outbox in the same transaction as the state
change, and this module consumes it.

That is the difference the modular-monolith field guide draws: direct calls for *questions*,
events for *facts*. "Did this payment settle" is a fact. Coupling the money path's latency and
failure modes to an email provider would be a bug.

Consequence: this module can be down without money movement being affected.

## Market context

Proactive incident communication was the single most-cited user frustration in the market brief
(`ARCHITECTURE.md` §2). v0 answers the minimum with `GET /system/status` and a hand-edited banner.
A real incident pipeline lands here.

## May depend on

`platform/` only. It is a consumer of events, not a caller of modules.
