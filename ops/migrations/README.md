# `ops/migrations`

Mongo schema migrations, applied by hand in order. `alembic/` next to the API is a leftover from
the Postgres plan in `PROMPT.md` §2 and is not wired to anything.

```bash
MSYS_NO_PATHCONV=1 docker cp ops/migrations/001_onboarding_kyc_schema.js gems-mongo:/tmp/m.js
MSYS_NO_PATHCONV=1 docker exec gems-mongo mongosh --quiet /tmp/m.js
```

Indexes are **not** here: `platform/db/indexes.py` creates them at startup, because
`create_index` is idempotent and an index is a performance fact, not a schema contract. Collection
validators are the schema contract, so they live here where the change is reviewable.

| File | What it does |
|---|---|
| `002_extracted_birth_date.js` | Adds required `extracted.birthDate` and turns `expiresOn` into an ISO date. Backfills existing cases from the CNP mask (which carries century, year and month; day defaults to 01) rather than inventing a date; deletes only cases where nothing is derivable. |
| `001_onboarding_kyc_schema.js` | Rewrites the `kycCases` and `users` validators for the four-step onboarding aggregate: nested `document` / `contact` / `otp` sub-documents, and string `_id` + string `kycCaseId` instead of ObjectId. |
