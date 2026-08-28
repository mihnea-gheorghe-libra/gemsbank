# Claude Code — Build Prompt: `gems-bank` (web banking app, agent-ready skeleton)

> **How to use this file.** It is the product brief: scope, rules, and the seven agent seams.
> `README.md` describes the repository as it actually stands; `CLAUDE.md` is the working
> agreement. Read all three before changing anything.

---

## 0. Role and mission

You are the lead engineer on a greenfield project. Build **`gems-bank`**: a web-based retail
banking application for the EU/Romanian market.

The mission is **not** to ship features. The mission is to lay down a **correct, boring, minimal
core** with **explicitly designed seams** so that a multi-agent AI layer (one orchestrator +
several specialised agents, some running in parallel) can be bolted on later **without touching
the money code**.

Optimise, in this order:

1. **Correctness of money.** The ledger is the product. Everything else is UI.
2. **Seams for the agent layer.** Every seam listed in §7 must exist in v0, even if empty.
3. **Small surface area.** Fewer files, fewer features, fewer dependencies. Empty folders with a
   `README.md` beat speculative code.
4. **Legibility.** Someone reading `README.md` and the folder tree should be able to
   predict where any future feature goes.

**This is a demo/educational system.** It is not a licensed credit institution, holds no real
funds, connects to no real payment rails, and stores no real PII or card data. Say so in the
README and put a persistent banner in the web UI footer. Never write code that pretends to
process real card numbers (PCI scope), and never invent a fake banking licence number.

---

## 1. Non-negotiable rules

Break any of these and the work is wrong, no matter how good it looks.

**Money**
- Money is **integer minor units** (`bigint` cents/bani) plus an **ISO 4217 currency code**.
  Floats and `Decimal`-in-JSON are forbidden across the wire. Format only at the view layer.
- **Double-entry only.** Every money movement writes ≥2 journal lines that sum to exactly zero
  per transaction, per currency. Enforce it in the database (constraint + trigger or a checked
  stored procedure), not only in Python.
- The journal is **append-only**. No `UPDATE`, no `DELETE` on posted entries. Corrections are
  reversal entries.
- **Balances are derived** from journal lines. A cached/snapshot balance is allowed only as an
  explicitly-labelled read model that can be rebuilt from the journal at any time.
- Posting is **atomic**: both legs commit or neither does, inside one DB transaction with
  `SERIALIZABLE` or `REPEATABLE READ` + retry.

**Safety of writes**
- Every state-changing endpoint requires an **`Idempotency-Key`** header. Uniqueness is enforced
  by a DB unique index; a repeat returns the **stored first response**, it does not re-execute.
- Every state-changing operation writes an **audit record** naming the **actor** (see §7.1).
- No business logic in HTTP handlers. Handlers parse → call an application service → serialise.

**Boundaries**
- Modules talk to each other **only** through their published `application/` ports. No
  cross-module imports of `domain/` or `adapters/`, no cross-module SQL joins, no cross-module
  foreign keys other than to `identity.users`.
- Add an automated boundary test (import-linter or a custom `pytest` that walks the AST) so
  violations fail CI. Boundaries that aren't enforced decay.

**Security**
- Argon2id for passwords. Short-lived access JWT + rotating refresh token stored server-side and
  revocable. Secrets only from env; commit `.env.example`, never `.env`.
- Sensitive operations (transfer above a threshold, changing credentials, adding a beneficiary)
  go through the **step-up / SCA port**, even though v0's implementation is a stub.

**Scope discipline**
- If a task is not in §4 (v0 scope), **do not build it**. Create the folder, write a `README.md`
  describing what will live there, move on.
- If you believe the architecture is wrong, **stop and say so** before coding. Then record the
  change in `README.md` in the same commit.

---

## 2. Stack

Chosen to match the developer's existing strengths (Python/FastAPI) and to make the future agent
layer trivial to add in the same language.

| Layer | Choice |
|---|---|
| Backend | **Python 3.12**, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), Alembic |
| Database | **PostgreSQL 16** |
| Frontend | **Next.js 15** App Router, TypeScript strict, Tailwind CSS v4 |
| UI kit | shadcn/ui primitives (Radix) — only the components actually used |
| Contracts | FastAPI-generated **OpenAPI 3.1** at `/openapi.json` |
| Tests | `pytest` + `httpx` (backend), Playwright smoke (web) |
| Tooling | `uv` or Poetry, `ruff`, `mypy --strict` on `platform/` and `modules/*/domain`, `pnpm`, ESLint |
| Local run | Docker Compose (mongo + api serving the static web client) |

**Swap point:** if a TypeScript-only stack is preferred later, only `backend/` changes. The
split between aggregate, service, adapters and routes and the DB schema port over directly.
Record the swap in `README.md`; do not do it unprompted.

Dependency budget for v0: **≤ 15 direct backend deps, ≤ 20 direct frontend deps.** If you want to
exceed it, justify each one first.

---

## 3. Phase 0 — Read the design archive before writing any UI

A design export produced with **Claude Design** will be placed at `design/export/`. It is an
**HTML archive** (loose `.html` + `.css` + assets, or a `.zip` you must unpack there first).

Do this **before** writing a single component:

1. `ls -R design/export/` and open every HTML file. If it is a zip, unpack in place.
2. Extract, into `design/tokens.extracted.json`:
   - colour palette (hex + the semantic role you infer: surface, on-surface, primary, positive,
     negative/debit, warning, muted, border),
   - type scale, font families, font weights actually used,
   - spacing scale, border radii, shadow definitions,
   - breakpoints.
3. Write those tokens as **CSS custom properties** in `frontend/styles/tokens.css`.
   **Components must never hardcode a hex value** — only `var(--…)`.
4. Record, in `README.md`:
   - a table mapping **each screen in the archive → the route** it becomes,
   - a table mapping **each repeated visual block → the component** you will create,
   - a list of screens in the archive that are **out of v0 scope** (they stay unbuilt; note the
     route as a stub),
   - anything in the design that conflicts with §6 (accessibility) or with the data model, and
     your proposed resolution.
5. Report the mapping to me and wait for confirmation before Phase 4.

**If `design/export/` is missing or empty:** do not invent a visual identity. Create the folder
with a `README.md` explaining what to drop there, build the UI with unstyled semantic HTML plus
neutral tokens, and tell me the archive is missing. Do not guess brand colours.

**Fidelity rule:** the archive dictates *look*. This prompt and `README.md` dictate *structure,
routes, and data*. Where they disagree, structure wins and you log it in `README.md`.

---

## 4. v0 scope — the bare minimum, and nothing else

### In scope

**Identity**
- Register, log in, refresh, log out. Argon2id, revocable refresh tokens.
- `GET /me`.
- Step-up port defined; the v0 adapter is a stub that accepts a fixed dev code and logs the
  challenge. Real SCA is future work.

**Accounts**
- List the current user's accounts; account detail.
- Multi-currency **at the schema level from day one** (an account has exactly one currency; a
  user may hold several accounts in different currencies). No FX conversion in v0.
- Balance is computed from the ledger, never stored as the truth.

**Ledger** (internal module, no public HTTP surface except read models)
- `journal_transactions` + `journal_entries`, append-only, balanced, idempotent.
- A `post_transaction(...)` application service — the single door through which money moves.
- Chart of accounts sufficient for v0: customer liability accounts, a bank settlement account, a
  fee revenue account, a suspense account.

**Payments**
- **Internal transfer only**: between two accounts of the same currency inside this system.
- Flow: validate → limits/policy check → Verification-of-Payee stub → optional step-up →
  `post_transaction` → outbox event.
- Beneficiaries: create and list. Nothing more.
- External rails (SEPA/SCT Inst), FX, standing orders: **not in v0**, but the payment state
  machine already accommodates them.

**Transactions view**
- Paginated, filterable (account, date range, direction) list built from a `transactions_view`
  read model over journal lines. Cursor pagination, not offset.

**Platform**
- `GET /health`, `GET /system/status` returning a hand-editable incident/status payload. The web
  app renders it as a dismissible banner. *(This exists in v0 on purpose: proactive incident
  communication was the single most-cited user frustration in the market brief.)*
- Structured JSON logging with a `correlation_id` propagated from the request header.

**Web**
- Routes: `/login`, `/register`, `/dashboard`, `/accounts/[id]`, `/transfer`, `/settings`.
- `/settings` ships **one real preference**: hide/show balances — persisted server-side. This is
  the seed of the "every UI change must be reversible by the user" principle from the brief.
- Status banner, empty states, error states, loading states. No dead links: unbuilt features are
  visibly marked "coming soon", never a 404.

**Ops**
- `docker-compose.yml`, `.env.example`, Mongo schema migrations in `ops/`, and a seed script
  creating 2 demo users with accounts in RON + EUR and ~30 realistic transactions.

### Explicitly NOT in v0

Cards, card controls, KYC/onboarding video, FX and multi-currency conversion, open banking /
account aggregation, savings and investments, notifications and push, joint accounts, business
accounts, admin back-office, chatbot, **and the entire agent layer**.

For each of these: build nothing. A feature folder appears the day its first line of code does.

**Deliberately taken out of this list since:**

- **Cards** — `backend/cards/` exists; see README.
- **Investments, real ledger-backed trading, gated by an investment account** —
  `backend/investments/` fetches prices and FX from public providers and converts to RON minor
  units, as before. It now also moves real money: `BuyInstrument` and `SellInstrument` run through
  `bus.execute` like every other write, each posting a single balanced transaction between the
  customer's `invest`-kind account and a `house:invest_suspense:{currency}` suspense account (the
  same demo-treasury pattern as `house:fx`). This is a deliberate, explicitly requested and
  approved deviation from the original "real ledger-backed trading stays out of scope" note — see
  README.md ("Investments — real prices, real trades") for the reasoning and the guard chain.
  A trade is refused, both at the route (`require_investment_account`) and again inside the
  command handler (the actual enforcement boundary, consistent with every other feature), unless
  the customer already holds an active `invest`-kind account. Holdings are a derived read model —
  summed from the append-only `investmentOrders` collection, never stored as a mutable balance —
  the same "derive, don't store" discipline rule 4 requires of the ledger.
- **FX conversion, display only, for investments** — the USD→RON conversion in
  `backend/investments/` is presentational, applied to market prices. It moves no money.
- **Currency exchange** — `backend/exchange/` exists; see README. A customer can convert RON into
  EUR or USD (and back) at a live rate, opening the target-currency account on the fly if needed.
  This is real, ledger-backed money movement, explicitly requested and approved as a deviation —
  it does **not** mean payments convert currency: `payments.transfer` still requires the source
  and target account to share a currency (`guard_same_currency`), unchanged. Exchange is the one
  sanctioned place where an account's currency boundary is crossed, and it does so as two
  correlated, single-currency journal transactions against a `house:fx` suspense account per
  currency — never a mixed-currency entry, so rule 2 (double-entry, sums to zero *per currency*)
  still holds.
- **Savings — real term deposits, real savings goal** — `backend/deposits/` and `backend/goals/`
  both open a real `savings`-kind pot account and move real money into and out of it via
  `LedgerService.transfer`, the same door `payments` already uses. This is a deliberate,
  explicitly requested and approved deviation from "savings" in the not-in-v0 list above — see
  README.md's "Portfolio" section for the mechanics and the demo simplifications (no
  early-withdrawal penalty, no compounding).
- **Credit applications, recorded but never decided** — `backend/credits/` lets a customer submit
  a real, persisted application against a product from `products.catalogue.CREDIT_PRODUCTS`. This
  adds a small new feature not named anywhere in this file, explicitly requested and approved. It
  changes nothing about eligibility: no application is ever approved or refused here, matching the
  agent-layer design in §7 — a future agent is still the seam for that decision.

### Definition of done for v0

- [ ] `docker compose up --build` gives a working app at `localhost:8000/app/` from a clean clone.
- [ ] A user can log in, see two accounts, open one, transfer money to the other, and see both
      balances and both transaction lists update correctly.
- [ ] Test: posting an unbalanced transaction is rejected **by the database**.
- [ ] Test: replaying a transfer with the same `Idempotency-Key` posts once and returns the same body.
- [ ] Test: a transfer exceeding the account's available balance is rejected with no partial write.
- [ ] Test: concurrent transfers from the same account never produce a negative balance.
- [ ] Test: the sum of all journal entries in the system is zero per currency, after seeding.
- [ ] Test: module boundary violations fail CI.
- [ ] Every seam in §7 exists and is exercised by at least one real call path.
- [ ] `README.md` matches the code that was actually written.

---

## 5. Folder structure

```
gems-bank/
├─ README.md
├─ CLAUDE.md
├─ PROMPT.md
├─ docker-compose.yml
├─ .env.example
├─ design/
│  ├─ export/                  Claude Design HTML archive
│  └─ tokens.extracted.json
├─ backend/
│  ├─ Dockerfile
│  ├─ requirements.txt
│  ├─ main.py                  FastAPI app, middleware, error handlers, static mount
│  ├─ config.py                settings from env
│  ├─ command_bus.py           SEAMS 2/4/5: the one write path
│  ├─ server/
│  │  └─ routes.py             HTTP endpoints + request schemas
│  ├─ database/
│  │  ├─ mongo.py              client, collections, indexes
│  │  ├─ repositories.py       aggregate <-> BSON
│  │  └─ records.py            audit, outbox, idempotency
│  ├─ onboarding/
│  │  ├─ service.py            commands, ports, handlers
│  │  ├─ kyc.py                KycCase aggregate
│  │  ├─ validation.py         username/password/PIN/contact rules
│  │  └─ adapters.py           clock, hasher, document extractor, OTP email
│  └─ helpers/
│     ├─ context.py            SEAMS 1/7: ids, Actor, correlation id, logging
│     └─ errors.py             error taxonomy -> HTTP mapping
├─ frontend/
│  ├─ index.html               script order = the module graph
│  ├─ main/register.jsx        RegisterPage + mount
│  ├─ components/{ui,rails,steps}.jsx
│  ├─ helpers/{api,i18n,messages}.js
│  └─ styles/{tokens,app}.css
└─ ops/                        Mongo schema migrations, applied by hand
```

A new backend feature is a new folder next to `onboarding/`, with the same four-file shape.
It reaches the outside world only through `command_bus.py` and `server/routes.py`.

---

## 6. Frontend requirements

- **Accessibility is a legal requirement, not a nicety.** The European Accessibility Act has been
  enforceable since 28 June 2025 and explicitly covers consumer banking services; the presumed-
  conformity standard is EN 301 549, which incorporates WCAG Level AA. Build to **WCAG 2.2 AA**:
  semantic landmarks, visible focus rings, 24×24px minimum targets, labelled inputs, no
  colour-only signalling for debit vs credit, keyboard-completable transfer flow, `prefers-
  reduced-motion` respected. Add `@axe-core/playwright` to the smoke test.
- **Money rendering**: one `<Money>` component. It receives minor units + currency and formats
  with `Intl.NumberFormat`. No ad-hoc formatting anywhere else.
- **Never optimistically show a transfer as complete.** Render the real state from the state
  machine, including `pending`.
- **i18n scaffold**: `ro` and `en` message files, `ro` default. Do not hardcode user-facing
  strings in components.
- Server Components by default; Client Components only where interaction demands it. Access
  tokens live in memory / httpOnly cookies, never `localStorage`.

---

## 7. The seven agent seams — build these now, use them later

This is the part that makes the app "agent-ready". Each seam must exist in v0 **and be used by
the human-driven flows**, so that the agent layer is a new *caller*, not a new *pathway*.

**7.1 Actor model.** `Actor = {kind: "user"|"system"|"agent", id, on_behalf_of, mandate_id?}`.
Every command, audit row and journal transaction carries an actor. In v0 `kind` is always `user`
or `system` — but the column, the type and the propagation already exist.

**7.2 Command bus.** Exactly one way to write: `bus.execute(Command, actor, idempotency_key)`.
The HTTP layer is a thin caller. Later, an agent is just another caller. No agent will ever get
its own private write path.

**7.3 Policy engine.** Before any command executes, a policy check runs: per-transaction limit,
daily limit, currency allowed, beneficiary allowed, actor allowed. It returns
`allow | deny | require_approval`. In v0 only static per-user limits are implemented, and
`require_approval` routes to the step-up stub. The same interface will later evaluate **agent
mandates** — scoped, capped, time-bounded, revocable grants modelled on the emerging agentic-
payments standards (Google's AP2 mandate envelope, now under FIDO Alliance governance, and the
card-network equivalents from Visa and Mastercard). Build the `mandates` table in the migration
with columns and no rows.

**7.4 Audit log.** Append-only, `(actor, action, entity, before, after, correlation_id, ts)`.
Non-optional. This is also the agent trace substrate.

**7.5 Outbox.** Every domain event is written to an `outbox` table in the same transaction as the
state change. In v0 a trivial poller logs them. Later this fans out to agents and notifications.

**7.6 Capability registry.** Every application service that an agent could plausibly call is
registered in `capabilities/` with: stable name, Pydantic input schema, Pydantic output schema,
side-effect class (`read` / `write` / `money-moving`), and required scope. In v0 this registry
drives nothing but a `GET /capabilities` debug endpoint and a test asserting every registered
capability actually resolves. Later, the MCP gateway generates its tool list **from this registry
alone** — an agent can never call something not registered.

**7.7 Correlation + trace context.** A `correlation_id` enters at the edge and flows through
command → policy → ledger → audit → outbox. Later, an agent run id and a span id join it, and one
agent-initiated transfer is fully reconstructable end to end.

### The future agent layer (design it in docs, build none of it)

When it is built, the agent orchestrator must be:

- **Orchestrator** (lead agent): classifies intent, plans, fans out to workers, aggregates,
  decides whether to answer or to propose an action. Never calls the DB.
- **Specialised workers**, several running in parallel where independent:
  `SupportAgent` (RAG over product docs), `InsightsAgent` (spend analysis, read-only),
  `PaymentsAgent` (proposes payment commands), `RiskAgent` (screens proposed commands),
  `OnboardingAgent` (guides non-standard onboarding — the weakest-covered area in the market).
- **Hard rules for the agent layer**:
  1. Agents call **capabilities only** (7.6), never SQL, never other modules directly.
  2. Any `money-moving` capability requires a valid mandate (7.3) **and** returns a *proposal*.
     Execution requires either an in-mandate auto-approval or an explicit human confirmation.
  3. Above a configurable amount, or for any irreversible action, a human confirms. Always.
  4. **Escalation to a human must be a first-class, always-visible option**, reachable within one
     turn — not hidden behind a bot. This is a direct lesson from the market brief.
  5. Treat every model input as untrusted: prompt injection is assumed. Validation and limits are
     enforced server-side in the policy engine, never by the prompt.
  6. Parallel fan-out only for **independent, read-only** subtasks. Money-moving work is
     sequential and single-writer.
  7. Every agent run produces a trace linked to the same `correlation_id` as its effects.

---

## 8. How to work with me

- **Ask before assuming** on anything that changes the data model, adds a dependency, or expands
  scope. Otherwise proceed.
- Prefer **one well-tested vertical slice** over four half-built modules.
- When you finish a phase, tell me: what you built, what you skipped and why, what surprised you,
  and the single riskiest thing in what you just wrote.
- If you catch yourself writing a feature "because a bank would have it" — stop. Check §4.
- Keep `README.md` true. A document that lies is worse than no document.

---
