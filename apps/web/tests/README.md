# Web tests — Playwright smoke

Small on purpose. This is a smoke suite, not a second test pyramid — the invariants that matter
are asserted in `apps/api/tests/`, against the database.

## The happy path

Log in, see two accounts, open one, transfer money to the other, see **both** balances and **both**
transaction lists update correctly.

That single flow is the v0 definition of done. Assert the *destination* account too — a transfer
that debits correctly and credits nothing passes a source-only check, and is exactly the bug
double-entry exists to catch.

## Accessibility assertions

`@axe-core/playwright` runs on every route in the smoke path. WCAG 2.2 AA is a legal requirement
under the European Accessibility Act, not a nice-to-have, so a violation fails the build.

Axe catches perhaps a third of real accessibility problems. It does not catch a transfer flow that
cannot be completed by keyboard — test that explicitly.

## Not here

Component unit tests, visual regression, load testing. If the smoke suite starts growing, ask
whether the thing being tested belongs in the backend suite instead.
