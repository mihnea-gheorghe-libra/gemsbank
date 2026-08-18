# `ledger` — the money core

**Status:** built in v0. **No public HTTP surface.** See ADR 0002.

## The one rule

Exactly one function writes to the journal:

```
ledger.application.post_transaction(lines, actor, idempotency_key, correlation_id, reference)
```

Only `payments` calls it. Nothing else — not `accounts`, not a script, not a migration, not an
agent — writes to `journal_transactions` or `journal_entries`. If you need money to move and you
are not in `payments`, you need a command, not a shortcut.

This module has **no `api/` folder**. That is deliberate: there is no HTTP route that can reach the
posting engine directly.

## What it owns

- `ledger_accounts` — the chart of accounts. v0 needs: customer liability accounts, a bank
  settlement account, a fee revenue account, a suspense account.
- `journal_transactions` — one row per business money movement, carrying `actor_kind`, `actor_id`,
  `mandate_id`, `correlation_id`, `idempotency_key`.
- `journal_entries` — the lines. `direction` is `debit` or `credit`, `amount_minor bigint > 0`.

## Invariants (enforced by PostgreSQL, not by this code)

Balanced per currency; append-only; positive amounts; entry currency equals account currency;
unique idempotency key; no negative customer balance without an overdraft facility.

The Python here is the *convenient* path to a correct posting. The database is what makes an
incorrect posting impossible. Do not move an invariant up into Python to make a test easier.

## Reading a balance

Balances are **derived**: sum of credits minus sum of debits over a liability account. The
`account_balances` snapshot is a read model with a `rebuild()` function. When the snapshot and the
recomputation disagree, the journal is right and the snapshot is broken.

## Debit and credit, for whoever is about to get this backwards

Customer money is a **liability** of the bank. So:

- Customer receives money -> **credit** their liability account.
- Customer sends money -> **debit** their liability account.

An internal transfer of 100 RON from A to B is: debit A 100, credit B 100. Sums to zero. The
common early bug is inverting this, and it looks completely plausible in the UI until someone
reads a statement.

## May depend on

`platform/` only. It knows nothing about users, payments or HTTP.
