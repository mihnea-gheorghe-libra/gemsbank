# `api/` — router assembly, dependencies, exception handlers

The HTTP edge. **No business logic lives here.**

A handler does exactly four things:

1. Parse and validate the request (Pydantic v2).
2. Authenticate and build the `Actor` — from the session, **never** from the request body.
3. Call `bus.execute(command, actor, idempotency_key)`.
4. Serialise the result.

If a handler contains an `if` about money, it is in the wrong file.

## What lives here

- Router assembly — mounting each module's `api/` router.
- Shared dependencies: current user, correlation id, `Idempotency-Key` extraction.
- Exception handlers mapping `platform/errors.py` taxonomy to HTTP status codes. One mapping, in
  one place; handlers never build error responses by hand.
- Platform endpoints: `GET /health`, `GET /system/status`, `GET /capabilities`.

## The OpenAPI contract

FastAPI generates OpenAPI 3.1 from these routes. `make openapi` regenerates
`packages/contracts` into TypeScript types. The web app has **no hand-written request or response
types** — a hand-written type here is a schema change waiting to fail at runtime instead of at
build time.

CI should verify the committed contract matches the live spec. A stale generated client is a lie
that only shows up in production.

## Note on `ledger`

`ledger` has **no router**. There is no HTTP route that reaches the posting engine. Money moves
through `payments` or it does not move.
