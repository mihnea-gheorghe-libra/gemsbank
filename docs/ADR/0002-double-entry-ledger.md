# ADR 0002 — A double-entry ledger, with the invariants enforced by PostgreSQL

- **Status:** accepted
- **Date:** 2026-08-18
- **Affects:** `ARCHITECTURE.md` §4, `docs/diagrams/erd-core.mmd`, `seq-transfer.mmd`

## Context

The obvious design for a demo banking app is a `balance` column on `accounts` and an
`UPDATE accounts SET balance = balance ± :amount`. It is smaller, faster to write, and easier to
query.

It is also unable to answer the only question that ever matters after something goes wrong: *where
did this money come from, and where did it go?* A balance column records the present and destroys
the past. Every fix after a discrepancy becomes archaeology across application logs, and a
discrepancy is not hypothetical — it is the normal consequence of a partial failure, a retry, or a
bug in exactly the code we are least able to test exhaustively.

The same artefact answers four different questions from four different askers: an audit, a
customer dispute, a reconciliation, and — later — "what did the agent actually do?" That last one
is why this ADR is a prerequisite for the agent layer, not an accounting nicety.

## Decision

Money exists only as **journal entries**. Every movement writes one `journal_transactions` row and
two or more `journal_entries` lines that sum to zero per currency. Customer money is a
**liability** of the bank, per standard practice.

**Amounts are `bigint` minor units plus an ISO 4217 code.** No floats, no `Decimal` on the wire.
Formatting happens once, at the view layer, in `<Money>`.

**Balances are derived**: `SUM(credits) − SUM(debits)` over a liability account. An
`account_balances` snapshot is permitted strictly as a read model with a `rebuild()` function and
a test asserting snapshot equals recomputation. When they disagree, **the journal is right**.

The invariants live in the **database**, not in Python:

1. Balanced — a deferred constraint trigger checks `Σ debits = Σ credits` per currency at commit.
2. Append-only — `UPDATE`/`DELETE` on `journal_entries` revoked at the role level *and* blocked by
   a trigger. Corrections are new reversal transactions referencing the original.
3. `CHECK (amount_minor > 0)` — direction carries the sign, never the amount.
4. An entry's currency must equal its ledger account's currency.
5. `UNIQUE (idempotency_key)` on `journal_transactions`.
6. No negative customer balance without an explicit overdraft facility — enforced in the posting
   service under `SERIALIZABLE` with retry, plus a reconciliation test.

Exactly one function may write to the journal: `ledger.application.post_transaction`. Only
`payments` calls it.

## Consequences

**Good.** Money cannot silently appear or vanish; the DB refuses. Every leu is traceable to a
transaction, an actor and a correlation id. Balances cannot drift, because there is nothing to
drift from. Reversals are first-class instead of a `DELETE` someone regrets.

**Bad.** Reads are more expensive — a balance is an aggregate, not a column. Every write is at
least three rows. The chart of accounts is a concept the team must actually learn; getting the
debit/credit direction backwards is the most likely early bug, and it will look correct in the UI
until someone reads a statement.

**Neutral.** The journal grows monotonically. Retention partitioning is a known future migration
that should be planned *before* the table is large, not after.

## Why enforce in the DB rather than in Python

Because the Python is what changes. Handlers get refactored, services get called from new places,
and eventually something writes to the journal from a script, a migration, or a well-meaning
agent. A `CHECK` constraint and a trigger apply to all of them equally, including the paths nobody
anticipated. Application-level validation protects against the code you wrote; database-level
validation protects against the code you will write.

The acceptance test for this ADR is therefore not "unbalanced transactions are rejected" — it is
**"unbalanced transactions are rejected by the database"**, asserted by attempting a raw insert
that bypasses the service entirely.

## Alternatives considered

| Option | Why not |
|---|---|
| `balance` column with `UPDATE` | No history, no audit, drift is undetectable until it is expensive |
| Event sourcing the whole domain | Double-entry already gives an append-only money log; ES elsewhere is cost without a question it answers |
| Ledger as a separate service | ADR 0001 — distributed money movement is the thing we are avoiding |
| Amounts as `NUMERIC` | Safe in the DB, but invites `Decimal` across the wire and float in JS. Integers are unambiguous everywhere |

## Revisit when

The journal exceeds roughly 50M rows (plan partitioning), or a genuine multi-currency FX
requirement arrives — cross-currency movements need a second balancing convention and an FX
revaluation account, and that is a new ADR, not an edit to this one.
