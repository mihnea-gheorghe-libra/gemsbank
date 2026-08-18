# `cards` — README only in v0

**Status:** no code. Folder reserved. **Do not build without an explicit PCI decision.**

## Purpose

Card issuance, card lifecycle (order, activate, freeze, replace, close) and card controls
(per-channel limits, geo-blocking, contactless toggle).

## Future public port

`cards.application`:

- `list_cards(user_id) -> [CardSummary]`
- `issue_card(account_id, kind) -> Card`
- `set_card_state(card_id, state)` — active | frozen | closed
- `set_controls(card_id, controls)`

Card authorisations reach the ledger the same way everything else does: a command on the bus that
calls `ledger.post_transaction`. There is no card-specific money path.

## The constraint that matters

`PROMPT.md` §0: never write code that pretends to process real card numbers. A PAN — even a
masked one — in the data model drags this repo into PCI-DSS scope, and the whole reason `payments`
is one bounded module (ADR 0001) is to keep that scope narrow.

The design archive's screen 06 renders masked PANs, expiry dates and a reveal-PIN control. It is
deliberately unbuilt (`docs/DESIGN_NOTES.md` §4.6). `/cards` in the web app is a "coming soon"
stub.

If this module is ever built, the card reference stored here is a **token from an issuer
processor**, never a PAN.

## May depend on

`platform/`, and `accounts.application` for the funding account. Never `ledger` directly.
