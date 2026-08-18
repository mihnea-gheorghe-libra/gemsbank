# `payments` — built in v0, internal transfers only

**Status:** built. The only module that may call `ledger.application.post_transaction`.

## v0 scope

- Internal transfer between two accounts **of the same currency** inside this system.
- Beneficiaries: create and list. Nothing more.
- Cross-currency transfers are **rejected** — multi-currency exists at the schema level, FX does not.

## The flow

Per `docs/diagrams/seq-transfer.mmd`:

```
validate -> policy check -> Verification of Payee (stub) -> step-up if required
         -> payments.create_payment(pending)
         -> ledger.post_transaction(...)        <- the only money door
         -> payments.mark(settled)
         -> audit row + outbox event            <- same DB transaction
```

Every arrow is a seam an agent will traverse later. There is no shortcut path, for anyone.

## State machine

`draft -> validated -> awaiting_approval? -> pending -> settled | rejected | failed`, plus
`reversed` reachable only from `settled`. See `docs/diagrams/state-payment.mmd`.

External rails will insert `submitted -> accepted_by_scheme` between `pending` and `settled`
**without changing the earlier states**. That is why the enum already has room for them.

The UI never optimistically shows a transfer as complete — it renders the real state, `pending`
included.

## Public port

`payments.application`:

- `transfer_internal(cmd, actor) -> TransferResult`
- `list_beneficiaries(user_id)` / `create_beneficiary(cmd, actor)`
- `get_payment(payment_id, actor)`

Registered in `capabilities/`. `payments.propose_internal_transfer` is the `money-moving` entry an
agent will eventually call, and it returns a **proposal**, never a completed transfer.

## The VoP stub

`adapters/vop_stub.py` implements the Verification-of-Payee port. It lives here rather than in
`compliance/` only because that module has no code yet; moving it is the first task when
`compliance` is built. The port interface will not change.

`no_match` warns the payer **before** execution, per the Instant Payments Regulation.

## May depend on

`platform/`, `ledger.application`, `accounts.application`, `identity.application` (step-up port).
Never another module's `domain/` or `adapters/`.
