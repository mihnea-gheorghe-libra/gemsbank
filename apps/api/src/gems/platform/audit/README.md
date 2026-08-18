# Seam 4 — Audit log

Append-only. `(actor, action, entity_type, entity_id, before, after, correlation_id, ts)`, plus a
nullable `agent_run_id` that stays null in v0.

**Non-optional.** Every state-changing operation writes one, in the same DB transaction as the
change. An audit row that can be written separately is an audit row that can be missing.

## Why `before` and `after` rather than a message

Because "user updated preferences" does not answer a dispute and "the amount changed from X to Y"
does. Diffable state is evidence; prose is a log line.

## This is also the agent trace substrate

When the agent layer lands, `agent_run_id` joins the existing `correlation_id`, and one
agent-initiated transfer becomes reconstructable end to end: which run, under which mandate, which
policy verdict, which journal transaction. That is only possible if the rows were being written
all along — which is why this is built in v0, for human traffic, with no agent in sight.

## Rules

- Append-only. No `UPDATE`, no `DELETE`. Same discipline as the journal.
- Never log a secret, a token, a password hash or a full PAN into `before`/`after`. Redact at the
  write, not at the read.
- The actor is never optional and never defaulted.
