# `gems-bank` — Architecture

**Status:** design baseline for v0. Last reviewed: 2026-08-18.
**Audience:** anyone (human or coding agent) writing code in this repo.
**Rule:** if the code and this document disagree, one of them is a bug. Fix both in the same PR.

Diagrams live in `docs/diagrams/*.mmd` and are referenced inline below.

---

## 1. What this is

A web-based retail banking application for the EU/RO market, built as a **modular monolith** with
a **double-entry ledger** at its core and **seven explicit seams** that let a multi-agent AI layer
be added later without modifying the money-handling code.

It is a demo system. No licence, no real funds, no real rails, no real PII.

### 1.1 What it is optimised for

| Priority | Consequence in the design |
|---|---|
| Money correctness | Double-entry, DB-enforced invariants, append-only journal, derived balances |
| Safe retries | Idempotency keys on every write, unique in the DB |
| Later agent layer | Actor model, command bus, policy engine, capability registry — present from day one |
| Small surface | v0 does internal transfers and nothing else |
| Auditability | Every write produces an audit row and an outbox event |
| Reversibility of UI change | User preferences are server-side and user-controlled from v0 |

### 1.2 Deliberate non-goals for v0

External payment rails, FX, cards, KYC, open banking, investments, notifications, business
accounts, admin tooling, and the agent layer itself. Each has a folder and a README; none has code.

---

## 2. Market and regulatory context that shaped this

The design responds to specific, documented pressures rather than generic "best practices".

**From the Romanian market brief (10 apps, 2025–2026).** The most-cited user frustrations were,
in order: unannounced downtime with no proactive communication; painful re-authentication when
changing phone or number, especially for the diaspora; slow onboarding for non-standard cases;
support that hides the escape hatch to a human behind a bot; and redesigns that remove
user control without an opt-out. No app on that market wins on reliability *and* feature depth
simultaneously, and **no banking chatbot in Romania can execute a transaction** — they all stop at
guidance. That last gap is the reason this architecture treats "an agent that can act, safely" as
the primary extension axis.

Design responses baked into v0: a `/system/status` endpoint and an in-app incident banner; a
step-up port that is device-and-channel agnostic rather than SMS-shaped; a hide-balances
preference as the seed of a reversible-personalisation policy; and an escalation-to-human rule
written into the agent layer's constitution before a single agent exists.

**Regulatory context.** The design assumes an EU deployment.

- **Instant Payments Regulation.** Verification of Payee — checking that the payee name matches
  the IBAN and warning the payer on mismatch — has been mandatory for euro-area PSPs since
  9 October 2025 for SEPA credit transfers. v0 implements a **VoP port with a stub adapter**, in
  the payment flow, in the right place. Wiring a real provider later is an adapter swap.
- **PSD3 / PSR.** Politically agreed 27 November 2025, with final compromise texts published in
  April 2026 and application expected around 2028. It generalises VoP across all credit transfers,
  shifts more APP-fraud liability onto PSPs, requires real-time transaction monitoring, mandates a
  **consent/authorisation dashboard** for third-party access, and keeps the two-factor SCA rule
  while newly permitting two inherence factors. Structural consequences here: the policy engine
  and audit log exist from day one, `compliance/` is a first-class module, and `/settings` is
  designed to grow a permissions dashboard.
- **European Accessibility Act.** Enforceable since 28 June 2025 and explicitly covering consumer
  banking services and their authentication flows; conformity is presumed via EN 301 549, which
  incorporates WCAG Level AA. The frontend targets **WCAG 2.2 AA**.
- **DORA / operational resilience.** Drives the health, status, structured-logging and
  correlation-id requirements.

**Agentic-payments standards to track, not to implement yet.** Google's Agent Payments Protocol
(AP2) defines signed *mandates* — Intent, Cart, Payment — as verifiable credentials proving what
a user authorised, what the agent selected and what was charged; it was donated to the FIDO
Alliance in 2026. Visa and Mastercard run network-specific equivalents (Trusted Agent Protocol /
Intelligent Commerce, Agent Pay with Agentic Tokens). The common shape across all of them —
**scoped, capped, time-bounded, revocable, cryptographically attributable authority** — is what the
`mandates` table and the policy engine are shaped to hold.

---

## 3. Architectural style

### 3.1 Modular monolith, hexagonal inside each module

One deployable backend. Inside it, modules bounded by business capability, each a small
hexagonal application: `domain` (pure), `application` (use cases + ports), `adapters` (DB, HTTP
clients, stubs), `api` (HTTP surface).

Rationale: a small team, an unconsolidated domain, and strong transactional consistency
requirements across accounts, ledger and payments. Microservices would buy independent deployment
we do not need, at the cost of distributed money movement, which is the one thing we cannot afford
to get wrong. The industry consensus in 2026 has swung the same way for teams of this size, and
keeping payment logic in a single well-bounded module also keeps future PCI audit scope narrow.
Extraction later is mechanical **if and only if** the boundaries were enforced — hence the
architecture tests.

See `docs/diagrams/c2-containers.mmd` and `docs/diagrams/c3-backend-modules.mmd`.

### 3.2 Dependency rule

```
api  →  application  →  domain
 ↓          ↓
adapters ───┘         (adapters implement ports defined in application)

any module  →  platform/         (allowed, one direction only)
platform/   →  any module        (forbidden)
module A    →  module B.domain   (forbidden)
module A    →  module B.application  (allowed, via published port only)
```

`ledger` is special: it has **no public HTTP surface**. Money moves only through
`ledger.application.post_transaction`, called by `payments`. Nothing else may write to the journal.

### 3.3 Module map

| Module | Owns | v0 status |
|---|---|---|
| `identity` | users, credentials, sessions, step-up port | built |
| `accounts` | accounts, currency, ownership, balance read model | built |
| `ledger` | chart of accounts, journal, posting engine | built |
| `payments` | transfers, beneficiaries, payment state machine | built, internal transfers only |
| `compliance` | VoP, limits, screening, monitoring | README only (VoP stub lives in `payments` adapters for now) |
| `cards` | card issuance, controls | README only |
| `insights` | categorisation, spend analytics | README only |
| `notifications` | channels, templates, delivery | README only |

`platform/` is the shared kernel: money, ids, errors, actors, command bus, policy, idempotency,
audit, outbox, observability. It contains no business rules.

---

## 4. The ledger

See `docs/diagrams/erd-core.mmd`.

### 4.1 Model

- `ledger_accounts` — the chart of accounts. Every row has a `type`
  (`asset` | `liability` | `equity` | `revenue` | `expense`), a `currency`, and an optional link
  to a customer-facing `accounts.account`. Customer money is a **liability** of the bank.
- `journal_transactions` — one row per business money movement. Carries `actor_kind`, `actor_id`,
  `correlation_id`, `idempotency_key`, `posted_at`, `reference`.
- `journal_entries` — the lines. `direction ∈ {debit, credit}`, `amount_minor bigint > 0`,
  `currency`, FK to `ledger_accounts` and to `journal_transactions`.

### 4.2 Invariants, enforced in the database

1. **Balanced.** For every `journal_transaction`, per currency:
   `Σ debits = Σ credits`. Enforced by a deferred constraint trigger at commit time.
2. **Append-only.** `UPDATE`/`DELETE` on `journal_entries` are revoked at the role level and
   blocked by a trigger. Corrections are new reversal transactions referencing the original.
3. **Positive amounts.** `CHECK (amount_minor > 0)`; direction carries the sign.
4. **Single currency per entry**, and an entry's currency must equal its ledger account's currency.
5. **Idempotent.** `UNIQUE (idempotency_key)` on `journal_transactions`.
6. **No negative customer balance** without an explicit overdraft facility: enforced in the
   posting service under `SERIALIZABLE` with retry, plus a reconciliation test.

### 4.3 Balances

Balances are **derived**: `SUM(credits) − SUM(debits)` over a liability account. A
`account_balances` snapshot table is permitted purely as a read model with a `rebuild()` function
and a test asserting snapshot equals recomputation. If they ever disagree, the journal is right.

### 4.4 Why double-entry for a demo app

Because single-entry lets money appear and disappear silently, and every fix after that is
archaeology. The journal is the only artefact that can answer "where did this leu come from and
where did it go" — which is exactly the question an audit, a dispute, a reconciliation, and a
misbehaving agent all ask.

---

## 5. Write path

See `docs/diagrams/seq-transfer.mmd` and `docs/diagrams/state-payment.mmd`.

```
HTTP handler
  → parse + authenticate → build Actor
  → CommandBus.execute(TransferCommand, actor, idempotency_key)
       → Idempotency: seen this key? → return stored response, stop
       → Policy:  allow | deny | require_approval
       → Compliance: Verification of Payee  (stub in v0)
       → Step-up if required                (stub in v0)
       → UnitOfWork [
             payments.create_payment(pending)
             ledger.post_transaction(...)      ← the only money door
             payments.mark(settled)
             audit.record(...)
             outbox.emit(PaymentSettled)
         ]
       → store response against the idempotency key
  → serialise
```

Every arrow above is also the arrow an agent will traverse later. There is no shortcut path, for
anyone.

**Payment states:** `draft → validated → awaiting_approval? → pending → settled | rejected |
failed`, plus `reversed` reachable only from `settled`. External rails will add
`submitted → accepted_by_scheme` between `pending` and `settled` without changing the earlier
states.

---

## 6. The seven agent seams

The agent layer is *not built* in v0. These seams are, because retrofitting them later means
touching the money code, which is the one thing we want to freeze.

| # | Seam | Where | v0 behaviour | What it becomes |
|---|---|---|---|---|
| 1 | **Actor** | `platform/actors.py` | always `user` or `system` | `agent` actors with `on_behalf_of` and `mandate_id` |
| 2 | **Command bus** | `platform/commandbus/` | the only write path for HTTP | the only write path for agents too |
| 3 | **Policy engine** | `platform/policy/` | static per-user limits; `require_approval` → step-up | evaluates agent **mandates**: scope, cap, expiry, beneficiary allowlist, revocation |
| 4 | **Audit log** | `platform/audit/` | every write, with actor | agent action provenance and dispute evidence |
| 5 | **Outbox** | `platform/outbox/` | logged by a trivial poller | fan-out to agents, notifications, analytics |
| 6 | **Capability registry** | `capabilities/` | `GET /capabilities` + a resolution test | the *sole* source of the MCP tool list |
| 7 | **Correlation/trace** | `platform/observability/` | `correlation_id` end to end | joined by `agent_run_id` and `span_id` |

### 6.1 Capability registry

Each entry declares: stable name, input schema, output schema, **side-effect class**
(`read` / `write` / `money-moving`), and required scope. Example shape:

```python
@capability(
    name="payments.propose_internal_transfer",
    effect=Effect.MONEY_MOVING,
    scope="payments:write",
    input=ProposeTransferIn,
    output=TransferProposalOut,
)
async def propose_internal_transfer(...): ...
```

The registry is the security boundary. An agent cannot call what is not registered, and
`money-moving` capabilities return **proposals**, never completed transfers, unless a mandate
authorises direct execution within its caps.

### 6.2 Planned agent topology

See `docs/diagrams/agents-orchestration.mmd` and `docs/diagrams/seq-agent-payment.mmd`.

Orchestrator-worker, which is the dominant production topology and the one Anthropic uses for its
own multi-agent research system: a lead agent decomposes the request, dispatches to specialised
subagents with explicit objectives, output formats, tool lists and boundaries, then aggregates.

Planned workers: `SupportAgent` (RAG, read-only), `InsightsAgent` (spend analysis, read-only),
`PaymentsAgent` (proposes commands), `RiskAgent` (screens proposals), `OnboardingAgent` (guides
non-standard onboarding).

**Constitution for that layer, fixed now:**

1. Agents call capabilities only. No SQL, no direct module access.
2. `money-moving` capabilities require a valid mandate **and** produce a proposal. Execution is
   either within-mandate auto-approval or explicit human confirmation.
3. Above a configurable threshold, or for anything irreversible, a human confirms. Always.
4. Escalation to a human is first-class and reachable in one turn. Never hidden behind the bot.
5. All model input is untrusted; prompt injection is assumed. Limits are enforced in the policy
   engine, server-side, never in the prompt.
6. Parallel fan-out only for independent read-only subtasks. Money movement is sequential,
   single-writer.
7. Every agent run emits a trace sharing the `correlation_id` of its effects.
8. Start with workflows, graduate to autonomy only where the task genuinely needs dynamic routing.
   Multi-agent orchestration carries real token and latency overhead and is not a default.

---

## 7. Frontend architecture

- Next.js App Router. Server Components by default; Client Components only for interaction.
- `apps/web/src/lib/api` is generated from the backend OpenAPI spec — no hand-written request
  types.
- Design tokens are extracted from the Claude Design HTML archive in `design/export/` into
  `design/tokens.extracted.json` and `apps/web/src/styles/tokens.css`. Components reference
  tokens only; hardcoded hex values are a lint error.
- One `<Money>` component owns all currency formatting.
- Accessibility target **WCAG 2.2 AA** (EN 301 549 / EAA), verified by `@axe-core/playwright`.
- `ro` and `en` message catalogues; `ro` default; no hardcoded user-facing strings.
- Tokens in memory or httpOnly cookies. Never `localStorage`.

---

## 8. Testing strategy

| Level | Scope |
|---|---|
| Domain unit | money arithmetic, entry balancing, payment state transitions |
| Invariant | unbalanced transaction rejected **by the DB**; system-wide sum = 0 per currency; snapshot = recomputation |
| Concurrency | parallel transfers from one account never go negative; serialisation retry works |
| Idempotency | same key twice → one posting, identical response body |
| Architecture | no cross-module imports; every registered capability resolves; no hardcoded hex in web |
| Integration | full transfer happy path + rejection paths over HTTP |
| E2E smoke | login → dashboard → transfer → balances updated, with axe assertions |

---

## 9. Deployment and operations

Docker Compose locally: `postgres`, `api`, `web`. `Makefile` targets: `up`, `down`, `migrate`,
`seed`, `test`, `lint`, `types`, `openapi`. CI runs lint, types, tests and architecture tests on
every push.

Observability: structured JSON logs with `correlation_id`, `/health` (liveness + DB), and
`/system/status` for the incident banner. When the agent layer lands, add per-run token and cost
counters — orchestrator-worker topologies are the expensive ones, and cost surprises there are
well documented.

---

## 10. Known limitations of v0

- Single database, single region, no read replicas, no partitioning. Retention partitioning of the
  journal is a known future migration and should be planned before the table grows.
- No real SCA, no real VoP, no real rails. All three are ports with stub adapters, deliberately.
- No FX. Multi-currency exists at the schema level only; cross-currency transfers are rejected.
- The status banner is hand-edited. A real incident pipeline is future work.
- The agent layer does not exist. Only its seams, its diagrams and its constitution do.

---

## 11. Decision log

Architecture decisions are recorded in `docs/ADR/`. Any change to §3, §4 or §6 requires a new ADR.
Amend, do not overwrite.
