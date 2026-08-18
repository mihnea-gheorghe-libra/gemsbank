# Seam 5 — Outbox

Every domain event is written to the `outbox` table **in the same transaction as the state
change**. That is the entire trick: either the payment settled and the event exists, or neither
happened. No dual-write, no lost events, no phantom notifications for money that never moved.

## v0 behaviour

A trivial poller reads unprocessed rows, logs them, stamps `processed_at`. That is it.

## What it becomes

Fan-out to `notifications`, to analytics, and to the agent layer. The pattern that matters, from
the modular-monolith field guide: **direct calls for questions, events for facts.**

"What is this account's balance?" is a question — a direct call to `accounts.application`.
"This payment settled" is a fact — an outbox event. `payments` must not call `notifications`; it
emits `PaymentSettled` and moves on. Coupling the money path's latency and failure modes to an
email provider would be a bug.

## Rules

- Emitted inside the unit of work, never after commit.
- Events are facts in the past tense: `PaymentSettled`, not `SendEmail`. An event that names its
  consumer is a method call wearing a costume.
- Payload is self-contained. A consumer should not need to query back to understand the event.
- Consumers must be idempotent — at-least-once delivery is the guarantee, not exactly-once.
- Carries the `correlation_id`.
