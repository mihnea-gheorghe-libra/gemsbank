# `/transfer`

The one write flow in v0. New-payment form (beneficiary, IBAN, amount, currency, reference) plus
`ConfirmTransfer`. Maps to design archive "Payments & transfers, SCREEN 05".

Submits to `POST /payments/transfers` with an `Idempotency-Key`. Renders the **real** payment
state from `docs/diagrams/state-payment.mmd` — never an optimistic "done" before the server says
`settled`.
