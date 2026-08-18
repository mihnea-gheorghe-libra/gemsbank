# CLAUDE.md — working agreement for `gems-bank`

Read this before every task. It is short on purpose.

## Context

Web banking app, EU/RO market. **Demo system**: no licence, no real funds, no real rails, no real
PII, no real card data. The point of the codebase is a correct money core plus explicit seams for
a future multi-agent AI layer.

Read in this order: `PROMPT.md` → `docs/ARCHITECTURE.md` → `docs/diagrams/*.mmd` → `docs/ADR/`.

## Commands

```bash
make up        # docker compose: postgres + api + web
make migrate   # alembic upgrade head
make seed      # demo users, accounts, transactions
make test      # pytest + playwright smoke
make lint      # ruff + eslint
make types     # mypy --strict on platform/ and modules/*/domain + tsc --noEmit
make openapi   # regenerate packages/contracts from the live spec
```

## Rules that must never be broken

1. **Money is `bigint` minor units + ISO 4217 code.** No floats, no `Decimal` on the wire.
2. **Double-entry only.** Every money movement = ≥2 journal lines summing to zero per currency,
   enforced by a DB constraint, not just Python.
3. **The journal is append-only.** Corrections are reversals. Never `UPDATE`/`DELETE` an entry.
4. **Balances are derived** from journal lines. Snapshots are read models that must be rebuildable.
5. **One money door**: `ledger.application.post_transaction`. Only `payments` calls it.
6. **One write path**: `CommandBus.execute(command, actor, idempotency_key)`. HTTP handlers are
   thin callers. So will agents be.
7. **Every write is idempotent** (DB-unique key, stored response replayed) and **audited** (actor,
   before/after, correlation_id) and **emits an outbox event** in the same transaction.
8. **No cross-module imports** except through a module's published `application/` port. No
   cross-module SQL joins. The architecture test enforces this — do not weaken it.
9. **Secrets from env only.** `.env` is never committed.
10. **No hardcoded colours in the web app.** Tokens from `design/export/` only.

## Scope discipline

If it is not in `PROMPT.md` §4, do not build it. Create the folder, write a `README.md` describing
what will live there and what its public port will be, and move on. Empty folders with good
READMEs are a deliverable, not a placeholder for guilt.

Never add a dependency without saying why. Budget: ≤15 direct backend, ≤20 direct frontend.

## The seven agent seams

`actors` · `commandbus` · `policy` · `audit` · `outbox` · `capabilities` · `observability`.

They exist in v0 and are exercised by the human-driven flows. When you add a feature, ask: does it
route through all seven? If a write path skips one, that path is wrong. The agent layer must be a
new *caller*, never a new *pathway*.

## Style

- Python: `ruff` defaults, type hints everywhere, `mypy --strict` on `platform/` and every
  `modules/*/domain`. Pydantic v2 for all boundary types. No `Any` in domain code.
- SQL: explicit migrations only. No autogenerate without reading the diff line by line.
- TypeScript: `strict`, no `any`, generated API types only. Server Components by default.
- Tests: name them after the invariant they defend, not after the function they call.
- Comments explain *why*. The code already says *what*.

## When you are unsure

Ask before: changing the data model, adding a dependency, expanding scope, or deviating from
`docs/ARCHITECTURE.md`. Proceed without asking on: naming, file layout inside a module, test
structure, refactors that preserve the public port.

If you deviate from the architecture doc, update the doc and add an ADR in the same commit.
A diagram that lies is worse than no diagram.

## End-of-task report

Every session ends with: what you built, what you deliberately skipped, what surprised you, and
the single riskiest thing in what you just wrote.
