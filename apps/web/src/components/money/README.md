# `components/money`

`Money` — the **only** currency formatter in the app. Takes minor units plus an ISO 4217 code,
formats with `Intl.NumberFormat`. Nothing else in the app formats a currency amount.

Also: `AccountTile`, `TransactionRow` (sign glyph + label, never colour alone — WCAG 1.4.1),
`TransactionList` (cursor-paginated), `ConfirmTransfer` (renders real payment state, never
optimistic).
