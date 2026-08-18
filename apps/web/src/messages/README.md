# i18n message catalogues

`ro.json` and `en.json`. **`ro` is the default** — the market is Romanian and the design archive's
demo data (Kaufland Băneasa, Enel Energie, salary from Nexo SRL) is Romanian throughout.

No hardcoded user-facing strings in components, including `aria-label`s. Both catalogues must have
the same key set — a missing key fails the build rather than rendering a raw key to a customer.
