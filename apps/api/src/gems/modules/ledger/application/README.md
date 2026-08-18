# `ledger/application`

Home of `post_transaction` — the **only** function anywhere that writes to the journal. Called
exclusively by `payments`. See `ledger/README.md` for the invariants this enforces alongside the
database.
