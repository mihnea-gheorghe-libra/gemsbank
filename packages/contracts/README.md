# `packages/contracts` — the generated API contract

**Generated. Do not hand-edit.**

## What is here

- `openapi.json` — OpenAPI 3.1, emitted by FastAPI from the live routes.
- `types.ts` — TypeScript types, generated from that spec by `openapi-typescript`.

Regenerate with `make openapi`.

## The rule

`apps/web/src/lib/api` contains **no hand-written request or response types**. Every type crossing
the network boundary comes from here.

A hand-written type at that seam does not fail when the schema changes — it keeps compiling and
starts lying. The failure surfaces in production, as a field that is silently `undefined`, in the
part of the app that displays money.

## CI

CI regenerates the contract and fails if the committed files differ from the live spec. Without
that check, "regenerate the contract" becomes a step people forget on exactly the PR where it
mattered.
