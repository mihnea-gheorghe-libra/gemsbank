# `ops/seed` — demo data

`make seed`. Idempotent: running it twice does not double the money.

## What it creates

- **2 demo users**, Argon2id passwords, credentials printed to stdout (this is a demo system;
  there is nothing to protect).
- Accounts in **RON and EUR** per user — multi-currency exists at the schema level from day one,
  and the seed proves it.
- The **chart of accounts**: customer liability accounts, a bank settlement account, a fee revenue
  account, a suspense account.
- **~30 realistic transactions**, matching the Romanian retail pattern in the design archive
  (groceries, utilities, salary, peer transfers, subscriptions) so the UI is exercised with
  plausible data rather than `test test test`.

## Non-negotiable

**The seed posts through `ledger.application.post_transaction`, like everything else.** It does not
insert journal rows directly, and it does not set balances.

A seed script with its own INSERT path is a second way to write money, and it will be the one that
drifts. It also silently defeats the test that matters most: after seeding, the sum of all journal
entries must be **zero per currency**. That test is only meaningful if the seed went through the
real door.

The actor for seeded transactions is `Actor(kind="system")` — seam 1, used for real, in v0.

## Opening balances

Funded from the bank settlement account, so the books balance. Money does not appear from nowhere,
not even in a demo.
