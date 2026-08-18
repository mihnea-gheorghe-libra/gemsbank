# `platform/db` — engine, session, base, unit of work

## Unit of work

One `UnitOfWork` per command. The bus opens it; the handler, the ledger posting, the audit row and
the outbox event all commit or roll back together. That atomicity is what makes seams 4 and 5
trustworthy rather than best-effort.

## Isolation

Money posting runs at **`SERIALIZABLE`** (or `REPEATABLE READ`) **with retry and exponential
backoff**. This is not optional: it is what stops two concurrent transfers from the same account
from each seeing sufficient funds and both succeeding.

Serialisation failures are **expected**, not exceptional. Retry them. The acceptance test for this
is "concurrent transfers from the same account never produce a negative balance".

## Rules

- **No cross-module SQL joins.** A query that joins `payments` to `identity` is a boundary
  violation wearing SQL syntax; the AST-based architecture test cannot see it, so this one is on
  you.
- No cross-module foreign keys except to `identity.users`.
- **Explicit migrations only.** Never trust `alembic --autogenerate` without reading the diff line
  by line — it cheerfully proposes dropping a constraint it does not understand, and the
  constraints are the product (ADR 0002).
- Async SQLAlchemy 2.0 throughout.
