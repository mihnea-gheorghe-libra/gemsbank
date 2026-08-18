# Seam 1 — Actor

```python
Actor(kind: Literal["user", "system", "agent"], id: UUID,
      on_behalf_of: UUID | None = None, mandate_id: UUID | None = None)
```

Every command, every audit row and every journal transaction carries one.

## v0 behaviour

`kind` is only ever `"user"` (a request from the web app) or `"system"` (seeding, the outbox
poller, scheduled work). **No agent actors exist.**

But the type has three members, the columns exist on `journal_transactions` and `audit_log`, and
the value propagates end to end. That is the whole point: when the first agent arrives it is a new
*value*, not a new *column*, and certainly not a new code path.

## Why `on_behalf_of` is separate from `id`

An agent acting for a user is two identities: the agent that decided, and the user whose money
moved. Collapsing them loses the ability to answer "which agent did this" during a dispute — and
that answer is exactly what an agentic-payments mandate is supposed to make provable (ADR 0003).

## Rules

- An `Actor` is constructed at the HTTP edge, from the authenticated session. Never from a request
  body — a caller must not be able to claim an identity.
- `mandate_id` is non-null only when `kind == "agent"`. Enforce it in the constructor.
- Never default an `Actor`. A missing actor is a bug, not a `system` action.
