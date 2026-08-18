# ADR 0003 — An actor model and seven seams, built before the agent layer exists

- **Status:** accepted
- **Date:** 2026-08-18
- **Affects:** `ARCHITECTURE.md` §6, `PROMPT.md` §7, `docs/diagrams/agents-orchestration.mmd`,
  `seq-agent-payment.mmd`

## Context

The market finding that shaped this project: **no Romanian banking chatbot can execute a
transaction.** They all stop at guidance (`REFERENCES.md`, market brief). The extension axis with
actual value is therefore "an agent that can act, safely" — and "safely" is an architecture
property, not a prompt.

The tempting sequence is: build v0, ship it, then add agents. That sequence fails, because every
one of the controls an acting agent needs — knowing *who* acted, capping *how much*, recording
*what happened*, restricting *what is callable* — is a change to the money path. By the time the
agent layer is a real project, the money path is the code nobody wants to touch, and the controls
get bolted on beside it instead of into it. That is how an agent ends up with its own private
write path.

## Decision

Build the seams in v0 and **use them for the human flows**, so that adding an agent later is a new
*caller*, never a new *pathway*.

| # | Seam | Where | v0 behaviour |
|---|---|---|---|
| 1 | Actor | `platform/actors.py` | `Actor{kind, id, on_behalf_of, mandate_id}` on every command, audit row and journal transaction. `kind` is only ever `user` or `system` in v0 — but the type, the column and the propagation exist |
| 2 | Command bus | `platform/commandbus/` | `bus.execute(command, actor, idempotency_key)` is the **only** write path. HTTP handlers are thin callers |
| 3 | Policy engine | `platform/policy/` | Runs before every command. Returns `allow \| deny \| require_approval`. v0 implements static per-user limits; `require_approval` routes to the step-up stub |
| 4 | Audit log | `platform/audit/` | Append-only `(actor, action, entity, before, after, correlation_id, ts)`. Non-optional |
| 5 | Outbox | `platform/outbox/` | Domain events written in the **same transaction** as the state change; a trivial poller logs them |
| 6 | Capability registry | `capabilities/` | Every agent-callable service registered with name, input/output schemas, side-effect class (`read`/`write`/`money-moving`) and required scope. Drives `GET /capabilities` and a resolution test |
| 7 | Correlation/trace | `platform/observability/` | `correlation_id` enters at the edge and flows through command → policy → ledger → audit → outbox |

Two tables ship **with the right shape and zero rows**: `mandates` and `agent_runs`. Writing them
into the first migration costs nothing now and avoids a schema change to the money tables later.

### The rule this exists to make enforceable

An agent is a `kind="agent"` actor calling the same bus, through the same policy engine, into the
same ledger, producing the same audit rows. There is no second door. If a future feature needs a
new write path, that is the signal that the design is wrong.

## Why `mandates` has that shape

The convergent answer across the emerging agentic-payments standards — Google's AP2 mandate
envelope (donated to the FIDO Alliance in 2026), Visa's Trusted Agent Protocol, Mastercard's Agent
Pay — is authority that is **scoped, capped, time-bounded, revocable and cryptographically
attributable** (`REFERENCES.md`). The columns follow directly: `scope` (which capabilities),
`max_amount_minor_per_tx` and `max_amount_minor_per_period` + `period` (caps),
`allowed_beneficiaries`, `valid_from`/`valid_until` (time bounds), `revoked_at` (revocation).

We implement none of the cryptography in v0. We reserve the shape, so that the policy engine which
today evaluates a static per-user limit can tomorrow evaluate a mandate through the same
interface.

## Consequences

**Good.** The agent layer becomes an integration project instead of a refactor of the money code.
Every human transfer in v0 exercises all seven seams, so they are tested by real traffic long
before an agent depends on them. The audit log doubles as the agent trace substrate.

**Bad.** v0 carries machinery it does not yet need: a command bus for a handful of commands, a
policy engine with one rule, a registry that drives one debug endpoint. This is visible overhead
and it will look like over-engineering to a reader who has not read this ADR. It also adds
indirection to every write, which makes stack traces longer and the "where does this actually
happen" question harder for a newcomer.

**Neutral.** The seams constrain how features get added. That is the point, and it will
occasionally be annoying.

## The constitution, fixed now

Written into `services/agent-orchestrator/README.md` before any agent exists:

1. Agents call **capabilities only**. No SQL, no direct module access.
2. `money-moving` capabilities require a valid mandate **and** return a *proposal*. Execution is
   either within-mandate auto-approval or explicit human confirmation.
3. Above a configurable threshold, or for anything irreversible, a human confirms. Always.
4. Escalation to a human is **first-class and reachable in one turn**. Never hidden behind the bot.
   This is a direct response to the loudest complaint in the market brief.
5. All model input is untrusted; prompt injection is assumed. Limits are enforced server-side in
   the policy engine, never in the prompt.
6. Parallel fan-out only for independent, read-only subtasks. Money movement is sequential and
   single-writer.
7. Every agent run emits a trace sharing the `correlation_id` of its effects.
8. Start with workflows; graduate to autonomy only where the task genuinely needs dynamic routing.

## Alternatives considered

| Option | Why not |
|---|---|
| Add the seams when the agent layer lands | Requires editing the money code at exactly the moment it is most frozen |
| Give agents a separate, restricted API | Two write paths means two sets of invariants, and the weaker one becomes the attack surface |
| Enforce limits in the agent's prompt | Prompt injection is assumed. A limit that a model can be talked out of is not a limit |
| Build the agent layer in v0 | `PROMPT.md` §4. One well-tested vertical slice first |

## Revisit when

The first real mandate is issued. At that point seam 3 needs mandate evaluation, seam 6 needs
scope checking wired to the MCP gateway, and both deserve their own ADR.
