# `compliance` — README only in v0

**Status:** no code. Folder reserved.

## Purpose

Everything that answers "is this payment allowed to happen, legally and operationally?" — as
distinct from `policy` in `platform/`, which answers "is this actor allowed to do this?".

## Future public port

`compliance.application`:

- `verify_payee(iban, name) -> VopResult{match | close_match | no_match | not_checked}`
- `screen_payment(payment) -> ScreeningVerdict` — sanctions/AML screening
- `monitor(transaction)` — real-time transaction monitoring (a PSR obligation)

## Why VoP lives in `payments` for now

Verification of Payee has been mandatory for euro-area PSPs on SEPA credit transfers since
9 October 2025 under the Instant Payments Regulation, and PSD3/PSR generalises it to all credit
transfers. It is therefore in the v0 payment flow **as a port with a stub adapter**, but the
adapter sits in `payments/adapters/` because there is no `compliance` module to hold it yet.

Moving it here is the first task when this module gets built. The port interface does not change —
that is the point of putting it behind one.

## May depend on

`platform/` only. Never on `payments`, `ledger` or `accounts` — compliance is called *by* the
payment flow, it does not reach into it.

## Blocked on

Nothing structural. It needs a real VoP provider and a screening list source, both of which are
integrations rather than architecture.
