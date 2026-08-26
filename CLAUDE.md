# CLAUDE.md — working agreement for `gems-bank`

Read this before every task. It is short on purpose.

## Context

Web banking app, EU/RO market. **Demo system**: no licence, no real funds, no real rails, no real
PII, no real card data. The point of the codebase is a correct money core plus explicit seams for
a future multi-agent AI layer.

Read in this order: `README.md` → `PROMPT.md`.

## Commands

```bash
docker compose up --build     # mongo + api; the api also serves frontend/ at /app/
docker compose logs -f api
ruff check backend
mypy backend

pip install -r backend/requirements.txt   # once; the suite needs pytest + pytest-asyncio
pytest                        # everything, from the repo root — no Docker, no Mongo, no network
pytest -m live_llm            # the graded prompt evals; needs Mongo + AZURE_OPENAI_* credentials
```

`pytest` from the repo root runs both test roots (`tests/` and `backend/tests/`) and must be green
before you push. It is hermetic: `backend/tests/conftest.py` pins every setting the suite reads, so
it does not matter whose `.env` is on disk or what the working directory is. Do not make a test
depend on `.env`; add the value there instead.

Schema migrations in `ops/` are applied by hand — see `README.md`.

## Rules that must never be broken

1. **Money is `bigint` minor units + ISO 4217 code.** No floats, no `Decimal` on the wire.
2. **Double-entry only.** Every money movement = ≥2 journal lines summing to zero per currency,
   enforced by a DB constraint, not just Python.
3. **The journal is append-only.** Corrections are reversals. Never update or delete an entry.
4. **Balances are derived** from journal lines. Snapshots are read models that must be rebuildable.
5. **One money door**: the ledger's `post_transaction`. Only `payments` and `exchange` call it —
   both go through the same function, so there is still exactly one place money moves from. A new
   feature does not get to call it without the same explicit approval `exchange` got; see README.
6. **One write path**: `bus.execute(command, actor, idempotency_key)` in `backend/command_bus.py`.
   HTTP handlers are thin callers. So will agents be.
7. **Every write is idempotent** (DB-unique key, stored response replayed) and **audited** (actor,
   before/after, correlation_id) and **emits an outbox event** in the same transaction.
8. **No cross-feature imports** except through a feature's `service.py`. No cross-feature queries
   against another feature's collection.
9. **Secrets from env only.** `.env` is never committed.
10. **No hardcoded colours in the web app.** Tokens from `design/export/` only, via
    `frontend/styles/tokens.css`.

## Scope discipline

If it is not in `PROMPT.md` §4, do not build it. Do not create a folder for it either — a feature
folder appears the day its first line of code does.

Never add a dependency without saying why. Budget: ≤15 direct backend, ≤20 direct frontend.

## The seven agent seams

`actors` · `commandbus` · `policy` · `audit` · `outbox` · `capabilities` · `observability`.

They live in `backend/helpers/context.py`, `backend/command_bus.py` and
`backend/database/records.py`, and are exercised by the human-driven flows. When you add a
feature, ask: does it route through all seven? If a write path skips one, that path is wrong. The
agent layer must be a new *caller*, never a new *pathway*.

## Style

- **Do not write comments or docstrings.** The code says what it does; naming carries the rest.
- Python: `ruff` defaults, type hints everywhere, `mypy --strict` on `helpers/` and every feature
  aggregate. Pydantic v2 for all boundary types. No `Any` in domain code.
- Mongo: explicit migration scripts in `ops/`, applied in order. Indexes at startup, not in
  migrations.
- Frontend: no build step. `index.html` script order is the module graph. Every user-facing string
  goes through `t()`; nothing is hardcoded in a component.
- Tests: name them after the invariant they defend, not after the function they call.

## Structure

One folder per concern, no deeper than two levels. `README.md` has the full map. A new backend
feature is a folder next to `backend/onboarding/` with the same shape: aggregate, `service.py`,
`validation.py`, `adapters.py`.

## When you are unsure

Ask before: changing the data model, adding a dependency, expanding scope, or moving a boundary.
Proceed without asking on: naming, file layout inside a feature, test structure, refactors that
preserve the public surface.

If you change the structure, update `README.md` in the same commit.

## End-of-task report

Every session ends with: what you built, what you deliberately skipped, what surprised you, and
the single riskiest thing in what you just wrote.
