# Architecture tests — the boundaries, enforced

These tests fail CI. They are not advisory.

`ARCHITECTURE.md` §3.1: extraction of a module later is mechanical **if and only if** the
boundaries held. Boundaries that are not enforced decay — so they are enforced here.

## What is asserted

| Test | Invariant |
|---|---|
| `test_no_cross_module_domain_imports` | No module imports another module's `domain/` or `adapters/`. Cross-module traffic goes through `application/` only |
| `test_platform_imports_no_module` | `platform/` never imports `modules/` or `capabilities/`. One direction only |
| `test_only_payments_calls_post_transaction` | `ledger.application.post_transaction` has exactly one caller |
| `test_ledger_has_no_router` | `ledger` exposes no HTTP surface |
| `test_every_capability_resolves` | Every registered capability resolves to a callable with matching input/output schemas |
| `test_money_moving_capabilities_return_proposals` | No `money-moving` capability posts directly |
| `test_every_write_endpoint_requires_idempotency_key` | No state-changing route without one |
| `test_no_hardcoded_hex_in_web` | No hex colour outside `apps/web/src/styles/tokens.css` |

Implementation: walk the AST (`import-linter` or a custom `pytest` that parses each file). AST,
not grep — a string search misses aliased imports and flags comments.

## The rule about this folder

**Do not weaken a test here to unblock a feature.** If one fires, either the design is wrong or
the code is. Fix one of them.

This is the failure mode ADR 0001 exists to prevent, and it is a likelier failure mode with coding
agents than with people: an agent optimising for "make CI green" will find deleting an assertion
much cheaper than restructuring an import. Treat a diff that edits this folder alongside a feature
as a red flag.

## What these tests cannot see

Cross-module **SQL joins**. The AST does not know what is inside a query string. That boundary is
enforced by review, not by CI — see `platform/db/README.md`.
