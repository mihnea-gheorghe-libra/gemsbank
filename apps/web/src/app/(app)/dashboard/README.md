# `/dashboard`

Account summary tiles (`AccountTile`) plus the recent transaction list. Maps to the design
archive's "Dashboard, SCREEN 03" — see `docs/DESIGN_NOTES.md` §2.

Server Component. Fetches `accounts.list_accounts` and a first page of
`accounts.list_transactions` server-side.
