# gems-bank

Web banking app for the EU/RO market. **Demo system**: no licence, no real funds, no real rails,
no real PII, no real card data. Built as a correct money core plus explicit seams for a future
multi-agent AI layer.

Currently one working screen: the four-step onboarding wizard (ID document → contact → email code
→ credentials).

## Run it

```bash
cp .env.example .env
docker compose up --build
```

- App: <http://localhost:8000/app/>
- API docs: <http://localhost:8000/docs>
- Mongo UI: <http://localhost:8081>

Without `RESEND_API_KEY` the OTP is not emailed; it comes back in the response as `devCode` and is
logged. That is intentional for local work.

Schema migrations in `ops/` are applied by hand, in order:

```bash
MSYS_NO_PATHCONV=1 docker cp ops/001_onboarding_kyc_schema.js gems-mongo:/tmp/m.js
MSYS_NO_PATHCONV=1 docker exec gems-mongo mongosh --quiet /tmp/m.js
```

Indexes are not migrations — `backend/database/mongo.py` creates them at startup.

## Structure

```
backend/
  main.py            FastAPI app, middleware, error handlers, static mount
  config.py          settings from env
  command_bus.py     the one write path: execute → audit → outbox → idempotency, one transaction
  server/routes.py   HTTP endpoints and request schemas
  database/
    mongo.py         client, collections, indexes
    repositories.py  aggregate ↔ BSON
    records.py       audit log, outbox, idempotency store
  onboarding/
    service.py       commands, ports, handlers
    kyc.py           the KycCase aggregate and its transitions
    validation.py    username, password, PIN, email, phone rules
    adapters.py      clock, password hasher, document extractor, OTP email
  helpers/
    context.py       ids, Actor, correlation id, JSON logging
    errors.py        error taxonomy → HTTP status

frontend/            no build step; index.html script order is the module graph
  index.html
  main/register.jsx  page state and flow orchestration, mounts the app
  components/        ui.jsx (primitives) · rails.jsx (step rail, agent panel) · steps.jsx
  helpers/           api.js (the only fetch caller) · i18n.js · messages.js (en + ro)
  styles/            tokens.css (the only place a hex value may appear) · app.css

design/              Claude Design export — source of truth for tokens
ops/                 Mongo schema migrations
```

React 18 and Babel standalone load from unpkg and transform the `.jsx` in the browser. Each file
attaches its exports to `window.GEMS`, so adding a file means adding a `<script>` tag in the right
place in `index.html`.

## How a write works

```
HTTP route → bus.execute(command, actor, idempotency_key)
                ├─ replay stored response if the key is known
                └─ one Mongo transaction:
                     handler → aggregate transition → repository save
                     audit record
                     outbox events
                     stored response
```

Nothing writes outside this path. When the agent layer arrives it becomes a second *caller* of
`bus.execute`, never a second pathway.

## Adding a feature

A feature is a folder next to `backend/onboarding/` with the same four-file shape: `kyc.py`-style
aggregate, `service.py` with its commands and handlers, `validation.py`, `adapters.py`. It reaches
the outside world through `command_bus.py` and `server/routes.py` and nothing else.

## Rules

See `CLAUDE.md`. The ones that shape every file: money is `bigint` minor units, double-entry only,
the journal is append-only, one money door, one write path, every write idempotent + audited +
emitting an event, and no hardcoded colours outside `frontend/styles/tokens.css`.

`PROMPT.md` is the product brief — scope, the seven agent seams, and what is deliberately not
built.
