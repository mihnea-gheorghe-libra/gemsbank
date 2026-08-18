# `agent-orchestrator` — designed here, built nowhere

**Status: no code. This README is the deliverable.**

The agent layer is **not in v0** (`PROMPT.md` §4). What exists in v0 is the seven seams that make
it addable without touching the money code (ADR 0003). This document fixes how it will work,
before anyone writes a line of it — because the constitution below is much harder to add to a
working agent than to an empty folder.

See `docs/diagrams/agents-orchestration.mmd` and `docs/diagrams/seq-agent-payment.mmd`.

---

## Why this layer is the point

No Romanian banking chatbot can execute a transaction. They all stop at guidance
(`docs/REFERENCES.md`, market brief). "An agent that can act, safely" is the extension axis with
real value — and *safely* is an architecture property, not a system prompt.

---

## Topology: orchestrator-worker

A lead agent decomposes the request, dispatches to specialised subagents with explicit objectives,
output formats, tool lists and boundaries, then aggregates. This is the dominant production
topology and the one Anthropic uses for its own multi-agent research system.

### Orchestrator (lead agent)

Classifies intent, plans, fans out to workers, aggregates, and decides whether to answer or to
propose an action.

**It never calls the database.** It never calls a module. It calls workers, and workers call
capabilities through the MCP gateway.

### Workers

| Agent | Job | Effect class |
|---|---|---|
| `SupportAgent` | RAG over product docs | `read` |
| `InsightsAgent` | Spend analysis, categorisation | `read` |
| `OnboardingAgent` | Guides non-standard onboarding — the weakest-covered area in the market brief | `read` |
| `PaymentsAgent` | Builds a payment **proposal** | `money-moving` |
| `RiskAgent` | Screens a proposal before it reaches the bus | `read` |

The three `read` workers may run **in parallel**. `PaymentsAgent` and `RiskAgent` run
**sequentially, single-writer**.

---

## The constitution

Eight rules. They are not guidelines and they are not negotiable per-feature.

**1. Agents call capabilities only.** No SQL, no direct module access, no HTTP to the API's own
routes. The MCP gateway generates its tool list from the capability registry (seam 6) and nothing
else, so an agent literally cannot call what is not registered.

**2. `money-moving` capabilities require a valid mandate and return a *proposal*.** Never a
completed transfer. Execution happens through the command bus, with a policy verdict, exactly as a
human's transfer does. There is one write path (seam 2) and the agent is a caller of it, not an
exception to it.

**3. Above a configurable amount, or for anything irreversible, a human confirms. Always.** No
mandate, however broad, removes this. "Irreversible" is a property of the action, not of the
amount.

**4. Escalation to a human is first-class, always visible, and reachable within one turn.** Never
hidden behind the bot, never gated on the agent deciding it has failed. This is a direct response
to the loudest complaint in the market brief: support that hides the escape hatch. If the UI shows
an agent, it shows the way past the agent in the same view.

**5. Every model input is untrusted. Prompt injection is assumed.** Limits are enforced
server-side in the policy engine (seam 3), never in the prompt. A transaction description, a
beneficiary name, a document the user uploaded — all of it is potentially adversarial text that
will reach a model's context. The defence is that the model cannot exceed a cap no matter what it
decides, because the cap is checked after it decides, by code it cannot address.

**6. Parallel fan-out only for independent, read-only subtasks.** Money-moving work is sequential
and single-writer. Concurrency plus money is how you get two transfers that each saw sufficient
funds.

**7. Every agent run produces a trace linked to the same `correlation_id` as its effects.**
`agent_runs` joins `audit_log` (seam 4) and `journal_transactions` on that id, so one
agent-initiated transfer is reconstructable end to end: the plan, the capability calls, the policy
verdict, the posting, the confirmation.

**8. Start with workflows; graduate to autonomy only where the task genuinely needs dynamic
routing.** Multi-agent orchestration carries real token and latency overhead and is not a default.
A deterministic workflow that solves the problem beats an agent that solves it more impressively.

---

## Mandates

A mandate is **scoped, capped, time-bounded, revocable and attributable** authority. That shape is
the convergent answer across Google's AP2 mandate envelope (donated to the FIDO Alliance in 2026),
Visa's Trusted Agent Protocol and Mastercard's Agent Pay — see `docs/REFERENCES.md`.

The `mandates` table ships in the **first migration**, with the right columns and **zero rows**:
`scope`, `max_amount_minor_per_tx`, `max_amount_minor_per_period`, `period`,
`allowed_beneficiaries`, `valid_from`, `valid_until`, `revoked_at`.

Evaluation belongs in `platform/policy/` (seam 3) — **not here**. An agent must not be able to
evaluate its own authority. This service proposes; the policy engine decides.

---

## Folder plan

| Folder | Contents |
|---|---|
| `src/orchestrator/` | Lead agent: intent classification, planning, fan-out, aggregation |
| `src/agents/` | The five workers, each with its own objective, boundaries and output schema |
| `src/tools/` | Thin client over the MCP gateway. **No business logic** |
| `src/mandates/` | Mandate *presentation* and lifecycle UX. Evaluation stays in `platform/policy/` |
| `src/memory/` | Conversation and run memory. Never a cache of balances — money is always read live |
| `src/traces/` | Run traces, spans, token and cost counters, written to `agent_runs` |
| `src/evals/` | Offline evaluation. An agent that touches money without a regression suite is not shippable |

---

## What must be true before this is built

- [ ] All seven seams exercised by human traffic in production, not just by tests.
- [ ] `mandates` and `agent_runs` migrated, with the policy engine reading mandates.
- [ ] MCP gateway generating tools from the capability registry alone.
- [ ] Per-run token and cost counters in place *before* the first fan-out — orchestrator-worker is
      the expensive topology and cost surprises there are well documented.
- [ ] An eval suite for every `money-moving` path, including adversarial inputs.
- [ ] The escalation-to-human path built and visible in the UI **first**.

That last one is not sequencing pedantry. If the escape hatch ships after the agent, it never
ships.
