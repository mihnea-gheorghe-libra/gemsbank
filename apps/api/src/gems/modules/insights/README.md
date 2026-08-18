# `insights` — README only in v0

**Status:** no code. Folder reserved.

## Purpose

Spend categorisation and analytics over the transaction read model. Archive screen 07
("Analytics & statistics") is the eventual UI; `/insights` is a "coming soon" stub in v0.

## Future public port

`insights.application`:

- `categorise(transaction) -> Category`
- `spend_by_category(user_id, period) -> [CategorySpend]`
- `recurring_payments(user_id) -> [RecurringPayment]`
- `spend_trend(user_id, period) -> Trend`

All of it is **read-only**. That is what makes `InsightsAgent` safe to fan out in parallel
(`ARCHITECTURE.md` §6.2) — no capability registered by this module may ever be `money-moving`.

## Design constraint

Reads from the `transactions_view` read model, never from `journal_entries` directly and never
across a module boundary in SQL. If a query needs data this module does not own, it asks the
owning module through its `application/` port.

Categorisation is derived data. It is never allowed to modify a journal entry — a miscategorised
transaction is a wrong label on an immutable fact, not a reason to touch the ledger.

## May depend on

`platform/`, `accounts.application`. Read-only.
