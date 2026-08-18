# `platform/` — the shared kernel

**It contains no business rules.** If you are about to write "a transfer may not exceed…" in here,
it belongs in a module.

## The dependency rule

```
any module  ->  platform/      allowed
platform/   ->  any module     FORBIDDEN
```

One direction, no exceptions. The architecture test enforces it. `platform/` importing a module is
how a shared kernel turns into a big ball of mud with extra steps.

## What lives here

| Path | What | Seam |
|---|---|---|
| `money.py` | `Money` value object — `bigint` minor units + ISO 4217. All arithmetic. | |
| `ids.py` | UUIDv7 generation — time-ordered, index-friendly | |
| `errors.py` | Domain error taxonomy and its mapping to HTTP status codes | |
| `db/` | Engine, session, declarative base, unit of work | |
| `actors.py` | `Actor{kind, id, on_behalf_of, mandate_id}` | **1** |
| `commandbus/` | `bus.execute(command, actor, idempotency_key)` — the only write path | **2** |
| `policy/` | `allow \| deny \| require_approval`, before every command | **3** |
| `idempotency/` | DB-unique key, stored first response replayed on retry | |
| `audit/` | Append-only `(actor, action, entity, before, after, correlation_id, ts)` | **4** |
| `outbox/` | Domain events, written in the same transaction as the state change | **5** |
| `observability/` | `correlation_id` propagation, structured JSON logging | **7** |

Seam 6 (the capability registry) lives in `capabilities/`, one level up — it references module
services, so it cannot sit under a package that is forbidden from importing modules.

## Why `Money` is a value object and not an int

Because an `int` does not know its currency, and the bug where 100 RON is added to 100 EUR is
silent, plausible and expensive. `Money` makes it a `TypeError`.

Never format in here. Formatting is a view concern and belongs in `<Money>` in the web app.

## `mypy --strict` applies

`platform/` and every `modules/*/domain` are strict-typed. No `Any`. This is the code where a type
error is a money error.
