# ADR 0001 — Modular monolith with hexagonal modules, not microservices

- **Status:** accepted
- **Date:** 2026-08-18
- **Affects:** `ARCHITECTURE.md` §3, `docs/diagrams/c2-containers.mmd`, `c3-backend-modules.mmd`

## Context

`gems-bank` moves money between accounts. The core operation — debit one account, credit another,
never lose or duplicate a leu — needs a single transactional boundary. The team is small, the
domain is not yet consolidated (we do not know where the seams between `payments`, `compliance`
and `ledger` will settle), and there is no independent-scaling pressure: v0 has one write path
and a handful of demo users.

Microservices would buy independent deployment we do not need and charge for it in distributed
transactions across the exact operation we cannot afford to get wrong. Sagas and compensating
transactions are a real answer to a real problem — but not to *this* problem, at *this* size.

Keeping payment logic inside one well-bounded module also keeps future PCI-DSS audit scope narrow
(`REFERENCES.md`, Nimble AppGenie 2026), which matters the moment cards stop being a README.

## Decision

One deployable backend (`apps/api`), internally divided into modules bounded by business
capability. Each module is a small hexagonal application: `domain` (pure, no I/O), `application`
(use cases and the ports it needs), `adapters` (DB, HTTP clients, stubs), `api` (HTTP surface).

Modules communicate **only** through another module's published `application/` port. No
cross-module `domain` or `adapters` imports, no cross-module SQL joins, no cross-module foreign
keys except to `identity.users`.

`platform/` is a shared kernel that every module may import and that may import no module. It
holds no business rules.

## Consequences

**Good.** One database transaction spans a whole transfer. Refactoring across module boundaries is
cheap while the domain is still moving. Local development is one `docker compose up`. Extraction
to a service later is mechanical — *if* the boundaries held.

**Bad.** Nothing forces the boundaries at runtime. A tired developer, or an agent optimising for
"make the test pass", will reach across a boundary because it is one import away. Deployment is
all-or-nothing: a bug in `insights` can take down `payments`.

**Neutral.** Scaling is vertical until it is not. That is a later problem with a known shape.

## The enforcement clause

Boundaries that are not enforced decay (`REFERENCES.md`, Viascom field guide). Therefore
`apps/api/tests/architecture/` contains a test that walks the AST of every module and **fails CI**
on a forbidden import. This test is load-bearing. Weakening it to unblock a feature is the failure
mode this ADR exists to prevent — if it fires, the design is wrong or the code is; fix one of
them, not the test.

## Alternatives considered

| Option | Why not |
|---|---|
| Microservices from day one | Distributed money movement; operational cost with no team to absorb it |
| Layered monolith (controllers/services/repos) | Layers do not bound a domain — everything ends up able to touch everything |
| Schema-per-module in one DB | Kept as an option; deferred. Same enforcement problem, more migration friction now |

## Revisit when

A module needs materially different scaling or availability from the rest (realistically:
`insights` under analytical load, or the agent layer's token-heavy traffic), **and** the boundary
test has been green without exemptions for the preceding quarter. Extract that module only.
