# ADR 0004 — Python/FastAPI backend, Next.js frontend, OpenAPI as the contract

- **Status:** accepted
- **Date:** 2026-08-18
- **Affects:** `ARCHITECTURE.md` §7, `PROMPT.md` §2, `docs/diagrams/c2-containers.mmd`

## Context

Two defensible stacks: TypeScript everywhere (one language, shared types, no contract generation
step), or Python for the backend and TypeScript for the frontend (two languages, a generated
contract at the seam).

Two things decide it. First, the team's existing depth is Python/FastAPI — and for code whose
defect mode is *silently wrong money*, fluency in the language beats elegance of the topology.
Second, the entire planned extension is an LLM agent layer, and that ecosystem's centre of gravity
is Python. Writing the orchestrator in the same language as the capability registry it exposes
means the tool schemas are the same Pydantic models the API already validates against — not a
second definition that can drift.

## Decision

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), Alembic |
| Database | PostgreSQL 16 |
| Frontend | Next.js 15 App Router, TypeScript strict, Tailwind CSS v4 |
| UI | shadcn/ui primitives (Radix), only the components actually used |
| Contract | FastAPI-generated OpenAPI 3.1 to TS types via `openapi-typescript` into `packages/contracts` |

The seam between them is the **generated OpenAPI contract**. `apps/web/src/lib/api` contains no
hand-written request or response types; `make openapi` regenerates them from the live spec. A
hand-written type at that boundary is a bug waiting for a schema change.

Dependency budget: **≤15 direct backend, ≤20 direct frontend.** Exceeding it requires a stated
justification per dependency. In a money system every dependency is also a supply-chain surface.

## Consequences

**Good.** The team writes the money code in the language it knows best. Pydantic v2 gives one
validation layer that serves HTTP boundaries, the capability registry and — later — agent tool
schemas. `mypy --strict` on `platform/` and every `modules/*/domain` makes the pure code actually
pure. PostgreSQL does the heavy lifting the ledger depends on (deferred constraint triggers,
`SERIALIZABLE`, role-level revocation) — none of which is stack-specific, which is what makes the
backend swappable.

**Bad.** Two languages, two toolchains, two CI jobs, two dependency graphs. The contract must be
regenerated or it lies — and a stale generated client fails at runtime, not at build time, unless
CI checks that the committed contract matches the live spec. It should.

**Neutral.** Async SQLAlchemy is more ceremony than sync for a workload that is not yet
concurrency-bound. Accepted, because the retry-under-`SERIALIZABLE` path is easier to reason about
once rather than to convert later.

## The swap point

If a TypeScript-only backend is preferred later, **only `apps/api` changes.** The hexagonal split
(`domain` / `application` / `adapters` / `api`), the module boundaries, the seven seams and the
entire database schema port over unchanged — none of them depend on Python. That is deliberate:
the language is the most reversible decision in this repo, and it is the one people argue about
most.

Do not do this unprompted. It is a new ADR superseding this one.

## Alternatives considered

| Option | Why not |
|---|---|
| TypeScript everywhere (NestJS / Hono + Drizzle) | Genuinely good; loses team fluency in the money code and puts the agent layer in the weaker ecosystem |
| Django | Batteries we do not want. The ORM and admin encourage exactly the cross-module coupling ADR 0001 forbids |
| Python backend + server-rendered templates | Drops the design system and the a11y tooling the EAA obligations rest on |
| gRPC instead of REST/OpenAPI | No browser-native client, no free spec-to-types path, and nothing here needs the throughput |

## Revisit when

Backend hiring shifts decisively to TypeScript, or the OpenAPI generation step becomes a recurring
source of production defects rather than a once-per-schema-change chore.
