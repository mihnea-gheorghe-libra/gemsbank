# `accounts` — built in v0

**Status:** built.

## Scope

- List the current user's accounts; account detail.
- **Multi-currency at the schema level from day one**: an account has exactly one currency, a user
  may hold several accounts in different currencies. **No FX conversion in v0.**
- Balance read model over the ledger.

## The balance rule

This module **reads** balances. It does not store them as truth and it does not write journal
entries. A balance is the sum of credits minus debits over the account's liability ledger account,
obtained through `ledger.application`.

The `account_balances` snapshot is a labelled read model with a `rebuild()`. If it ever disagrees
with recomputation, the journal is right (ADR 0002).

## Public port

`accounts.application`:

- `list_accounts(user_id) -> [AccountSummary]`
- `get_account(account_id, actor) -> AccountDetail`
- `get_balance(account_id) -> Money`
- `list_transactions(account_id, filters, cursor) -> Page[TransactionRow]`

`get_balance` and `list_transactions` are registered as `read` capabilities — they are what
`InsightsAgent` and the orchestrator's read-only fan-out will call.

## Transactions view

`list_transactions` reads a `transactions_view` read model over journal lines. **Cursor
pagination, not offset** — offset pagination over an append-only table shows duplicates and skips
rows as new entries land.

Filterable by account, date range and direction.

## IBANs

Synthetic and demo-only. They are not registered with any scheme and must never be presented as
real. Format-plausible, deliberately not valid for any live rail.

## May depend on

`platform/`, `ledger.application` (read), `identity.application` (ownership checks).
