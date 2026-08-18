# Seam 2 — Command bus

```python
result = await bus.execute(command, actor, idempotency_key)
```

**The only way to write.** HTTP handlers parse, build an `Actor`, and call this. They contain no
business logic.

## What the bus does, in order

1. **Idempotency** — has this key been seen? If yes, return the stored response and stop. Do not
   re-execute.
2. **Policy** (seam 3) — `allow | deny | require_approval`. `deny` stops here.
3. **Handler** — the module's application service, inside one unit of work.
4. **Audit** (seam 4) and **outbox** (seam 5) — in the same DB transaction as the state change.
5. **Store the response** against the idempotency key.

The `correlation_id` (seam 7) rides along the whole way.

## Why this exists in v0, with about four commands

Because the alternative is that the agent layer gets its own write path. Two write paths means two
sets of invariants, and the weaker one becomes the attack surface. An agent must be a new
*caller* of this bus, never a new pathway around it. See ADR 0003.

## Rules

- One command, one handler. No handler calls another handler — it calls application services.
- Commands are Pydantic v2 models. They are data, never behaviour.
- A handler that needs to move money calls `payments`, which calls
  `ledger.application.post_transaction`. Nothing else touches the journal.
- If you find yourself wanting to bypass the bus "just for this one endpoint", that endpoint is
  the bug.
