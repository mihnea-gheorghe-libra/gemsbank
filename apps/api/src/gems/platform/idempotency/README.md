# Idempotency

Every state-changing endpoint requires an **`Idempotency-Key` header**. Uniqueness is enforced by
a **DB unique index**, not by an application check — a check-then-act in Python has a race window
exactly wide enough for a double-tapped transfer button.

## Behaviour

A repeat of a seen key returns the **stored first response** — same status, same body. It does not
re-execute. That is the difference between "idempotent" and "safe to retry and probably fine".

`idempotency_keys(key PK, user_id, endpoint, response_status, response_body, created_at)`, and
separately `UNIQUE (idempotency_key)` on `journal_transactions` so the money layer has its own
guarantee independent of this table.

## Why two layers

Defence in depth. The `idempotency_keys` table protects the endpoint; the unique constraint on
`journal_transactions` protects the ledger. If a future write path forgets the first, the second
still refuses to post the same transaction twice. Given that "a future write path" eventually
means "an agent retrying after a timeout", this redundancy is cheap insurance.

## Rules

- Reserve the key **before** executing, in the same transaction.
- Scope keys to the user. A key from one user must never replay another's response.
- A key replayed with a *different* request body is a client bug — return 422, do not silently
  serve the old response.
