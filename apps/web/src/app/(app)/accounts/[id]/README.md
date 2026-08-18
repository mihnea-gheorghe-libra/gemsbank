# `/accounts/[id]`

Single account detail: balance, IBAN, and the full filterable transaction list
(`TransactionList`, cursor-paginated). Maps to design archive "Accounts & portfolio, SCREEN 04".

Ownership is checked server-side through `accounts.get_account(account_id, actor)` — never trust
the route param alone.
