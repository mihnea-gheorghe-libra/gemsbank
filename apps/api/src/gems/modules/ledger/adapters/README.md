# `ledger/adapters`

SQLAlchemy repositories for `journal_transactions`, `journal_entries`, `ledger_accounts` and the
`account_balances` snapshot. No business logic — the invariants live in the database (ADR 0002)
and in `ledger/domain`, not here.
