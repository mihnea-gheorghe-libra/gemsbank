# Integration tests — real PostgreSQL, real HTTP

These need the database, because most of what they assert **is** the database.

## The invariants that must be tested here, not in unit tests

| Test | Why it must hit the DB |
|---|---|
| Unbalanced transaction rejected | The assertion is that **PostgreSQL** rejects it. Insert raw, bypassing the service entirely — otherwise you are testing the Python you were trying not to trust |
| Journal is append-only | `UPDATE`/`DELETE` must fail at the role and trigger level |
| Idempotent replay | Same `Idempotency-Key` twice, one posting, **identical response body** |
| Insufficient funds | Rejected with **no partial write** — assert the journal is untouched, not just the status code |
| Concurrent transfers | Parallel transfers from one account never go negative; the `SERIALIZABLE` retry works |
| System-wide sum is zero | After seeding, per currency, across all journal entries |
| Snapshot equals recomputation | `account_balances` rebuilt from the journal matches |
| Full transfer over HTTP | Happy path plus every rejection path |

## The one that catches the most

**Concurrency.** Run the transfers genuinely in parallel against a real connection pool. A
sequential loop passes trivially and proves nothing — the bug it is looking for only exists when
two transactions read the same balance before either commits.
