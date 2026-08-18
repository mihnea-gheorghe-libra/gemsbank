# Seam 6 — Capability registry

Every application service an agent could plausibly call is registered here with a **stable name**,
a **Pydantic input schema**, a **Pydantic output schema**, a **side-effect class** and a
**required scope**.

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

## Side-effect classes

| Class | Meaning | Agent rule |
|---|---|---|
| `read` | No state change | Safe to fan out in parallel |
| `write` | Changes state, no money | Sequential; audited |
| `money-moving` | Touches the ledger | Requires a valid mandate **and** returns a *proposal* |

## v0 behaviour

The registry drives exactly two things: a `GET /capabilities` debug endpoint, and a test asserting
every registered capability actually resolves to a callable with matching schemas.

That is deliberately almost nothing. The registry is not useful in v0 — it is *correct* in v0, so
that it can be relied on later.

## What it becomes

**The sole source of the MCP gateway's tool list.** The gateway generates its tools from this
registry and nothing else, which means an agent **cannot call something that is not registered**.
That is the security boundary: not a prompt instruction, not a filter on the model's output — a
list that is generated from typed declarations in this repo.

## Why it lives here and not in `platform/`

It references module application services. `platform/` may not import modules (ADR 0001), so the
registry sits one level up, alongside `modules/`.

## Rules

- Names are **stable and namespaced**: `module.verb_noun`. A renamed capability is a breaking
  change to every mandate that scoped to it.
- No capability wraps a raw SQL query or reaches past a module's `application/` port.
- `money-moving` capabilities **never execute**. They return a proposal. Execution goes through the
  command bus with a policy verdict, exactly like a human's transfer does.
- Registering a capability is a deliberate act. Auto-registering every public function would turn
  the security boundary into a rubber stamp.
