# Seam 7 — Correlation and trace context

A `correlation_id` enters at the HTTP edge — from the request header if present, generated if not
— and flows through **command, policy, ledger, audit, outbox**. Every structured log line carries
it.

## v0 behaviour

Structured JSON logging with `correlation_id`. `/health` (liveness plus DB). `/system/status`
serving a hand-editable incident payload that the web app renders as a dismissible banner.

The status endpoint is in v0 on purpose: **unannounced downtime with no proactive communication
was the single most-cited user frustration in the market brief.** It is a two-field endpoint and a
banner, and it addresses the loudest complaint in the market. See `ARCHITECTURE.md` §2.

## What it becomes

`agent_run_id` and `span_id` join the `correlation_id`, so one agent-initiated transfer is fully
reconstructable: the run that planned it, the capability it called, the policy verdict, the
journal transaction, the audit row. Same id, one query.

Add per-run token and cost counters when the agent layer lands — orchestrator-worker topologies
are the expensive ones and cost surprises there are well documented.

## Rules

- Never log a secret, a token, or a full account identifier.
- The correlation id is propagated, never regenerated mid-request.
- Logs are JSON. A human-readable log is a log nobody can query during an incident.
