# gems-bank

Web banking app for the EU/RO market. **Demo system**: no licence, no real funds, no real rails,
no real PII, no real card data. Built as a correct money core plus explicit seams for a future
multi-agent AI layer.

Three working screens:

- **Sign in** — username + 6-digit PIN, with PIN recovery and password reset.
- **Create account** — the four-step onboarding wizard (ID document → contact → email code →
  credentials). Completing it opens three accounts and posts a demo opening balance.
- **Payments & transfers** — accounts with derived balances, the movements table (filter,
  search, cursor pagination), pending signatures, and the new-payment flow.

Sign in mints a **session token** (`sessions` collection). The frontend holds it in memory and
sends it as `Authorization: Bearer …`; a page refresh signs you out, which is the intended
behaviour while there is no refresh-token rotation (`PROMPT.md` §6: never `localStorage`).
After a successful sign in you land on a **dashboard mockup**: a static, frontend-only prototype
(`frontend/main/dashboard.jsx` and `frontend/components/dashboard-*.jsx`) covering Dashboard,
Payments, AI Assistant, Portfolio, Cards, Analytics and Settings. It is a deliberate, explicitly
approved deviation from `PROMPT.md` §4 — cards, investments, analytics and the chatbot are listed
there as *not in v0* — kept as UI only, with hand-authored demo data
(`frontend/helpers/dashboard-data.js`). The PIN-reveal screen (`AUTH.PinRevealScreen`) still runs
first whenever a flow surfaces the PIN (forgot-PIN, password reset); its "Close and continue"
action opens the dashboard mockup. Plain PIN sign-in opens it directly, since it has no PIN to
show — there is no separate "welcome" screen any more. There is still no session token: the real
dashboard and the `sessions` collection arrive together, later.

The **Cards** screen is the one exception: it has a real backend (`backend/cards/`) — issue a
virtual card, freeze/unfreeze, reveal PIN, set ATM/online limits, block permanently — but the
Cards screen itself still renders from `dashboard-data.js`, not from these endpoints. See
"Cards — a backend without a session" below before wiring it up.

## Run it

```bash
cp .env.example .env
# fill in MONGO_URI, and the OTP/lockout tuning values (OTP_TTL_SECONDS,
# PIN_MAX_FAILURES, PASSWORD_MAX_FAILURES, PASSWORD_LOCKOUT_SECONDS, ...) —
# they have no defaults in config.py on purpose, so the app will refuse to
# start without them.
docker compose up --build
```

- App: <http://localhost:8000/app/>
- API docs: <http://localhost:8000/docs>
- Mongo UI: <http://localhost:8081>

Without `RESEND_API_KEY` the OTP is not emailed; it comes back in the response as `devCode` and is
logged. That is intentional for local work. The same applies to the password-reset code.

The onboarding OTP lives for `OTP_TTL_SECONDS` — the customer is already looking at the screen when
it is sent, so it is short. The password-reset code lives for `RESET_CODE_TTL_SECONDS`, given more
time because it is read out of an inbox that may be a few minutes behind. Exact values are set per
environment in `.env`, not committed — see `.env.example`.

The frontend is served with `Cache-Control: no-store`. There is no build step and no fingerprinted
filenames, so a cached `.jsx` or `.css` would otherwise survive an edit and make you debug the
previous version.

Without `PIN_ENCRYPTION_KEY` the PIN cipher falls back to a well-known demo key and logs
`pin_cipher.dev_key_in_use` at startup. Fine locally, never anywhere else.

Schema migrations in `ops/` are applied by hand, in order:

```bash
MSYS_NO_PATHCONV=1 docker cp ops/001_onboarding_kyc_schema.js gems-mongo:/tmp/m.js
MSYS_NO_PATHCONV=1 docker exec gems-mongo mongosh --quiet /tmp/m.js
```

`004_payments_ledger_schema.js` is not optional. It creates `sessions`, `accounts`,
`journalTransactions`, `payments`, `beneficiaries` and the empty `mandates`, and it installs the
validator that makes the database refuse an unbalanced journal transaction. Without it the app
runs and the ledger loses its second line of defence.

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
    adapters.py      clock, document extractor, OTP email
  auth/
    service.py       commands, ports, handlers, the /me profile read model
    credentials.py   the AuthUser, Session and RecoveryCase aggregates and their transitions
    validation.py    username, PIN shape, new-password rules
    adapters.py      clock, reset-code email
  ledger/            the money core — no public HTTP surface except read models
    journal.py       JournalTransaction + JournalEntry; the balanced, append-only aggregate
    service.py       post_transaction — the one money door — plus balance and movement reads
    validation.py    ISO 4217 codes, minor-unit bounds
    adapters.py      clock
  accounts/
    account.py       the Account aggregate and its guards
    service.py       open, resolve by IBAN, list with balances derived from the ledger
    validation.py    IBAN mod-97 check and generation
    adapters.py      clock, the starter-account list
  payments/
    service.py       commands, ports, handlers, read models
    payment.py       the Payment state machine and the Beneficiary aggregate
    validation.py    reference, counterparty, category, cursor codec
    adapters.py      clock, limit policy, step-up stub, Verification-of-Payee stub
  helpers/
    context.py       ids, Actor, correlation id, JSON logging
    crypto.py        Argon2id hasher, AES-GCM PIN cipher
    errors.py        error taxonomy → HTTP status

frontend/            no build step; index.html script order is the module graph
  index.html
  main/app.jsx       chooses sign in vs register, mounts the app
  main/signin.jsx    sign in, PIN recovery, password reset, welcome, hands off to the dashboard
  main/register.jsx  onboarding page state and flow orchestration
  main/dashboard.jsx post-login dashboard mockup: screen state, chat state, mock-data wiring
  components/        ui.jsx (primitives) · rails.jsx (step rail, agent panel) · steps.jsx ·
                     auth.jsx (sign-in forms, PIN panel, welcome) ·
                     dashboard-widgets.jsx (segmented control, bars, donut, progress, amount) ·
                     dashboard-shell.jsx (sidebar, topbar, agent dock, new-payment dialog) ·
                     dashboard-screens.jsx (home, payments, chat, portfolio, cards, analytics, settings)
  helpers/           api.js (the only fetch caller) · i18n.js · messages.js (en + ro) ·
                     people.js (name formatting for display) ·
                     dashboard-data.js (hand-authored demo data for the dashboard mockup)
  styles/            tokens.css (the only place a hex value may appear) · app.css · dashboard.css

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

`CommandResult` has two output channels: `data` is stored and replayed under the idempotency key;
`sensitive` is merged into the HTTP response and never persisted anywhere. Use `sensitive` for
anything a replay must not hand out twice.

Failed authentication is the one place a handler writes outside the command transaction: the
attempt counter is saved with no session before the error propagates, because the rollback would
otherwise erase the evidence of the failure. `onboarding` does the same for OTP attempts.

## How money moves

One collection, `journalTransactions`, holds the whole ledger. Each document is one transaction
in one currency with an embedded `entries` array, and it is written by exactly one function —
`ledger.post_transaction`, called only from `payments`.

Entry amounts are **signed integer minor units, from the account holder's point of view**: the
account that receives gets `+`, the account that pays gets `−`. A customer balance is therefore
the plain sum of that account's entries, and it is always derived — there is no balance column
anywhere. House accounts (`house:settlement:RON`, `house:fee_revenue:*`, `house:suspense:*`) are
chart-of-accounts constants, not rows in `accounts`; the settlement account carries the negative
counter-leg of every demo deposit.

The balanced-transaction rule is enforced **by Mongo**, not only by Python. The validator in
`ops/004_payments_ledger_schema.js` carries three `$expr` clauses: entries sum to zero, at least
two entries, no entry for zero. Verified by hand:

```
ACCEPTED  balanced pair          REJECTED  unbalanced pair
ACCEPTED  three legs balanced    REJECTED  single leg
                                 REJECTED  zero-amount leg
```

The journal is append-only: `MongoJournalRepository` has `append` and reads, and no update path.
Do not add one — corrections are reversal entries (`TransactionKind.REVERSAL`, unused so far).

A payment is a separate aggregate with its own state machine, so the ledger stays ignorant of
intent:

```
draft ──(policy: allow)────────────────────────────────► posted
  │                                                        ▲
  └──(policy: require_approval)─► awaiting_signature ──────┘
                                        │  (sign with the step-up code)
  └──────────────────────────────► rejected
```

`pending` exists in the enum and is unreachable in v0. It is where SEPA/SCT Inst lands the day
external rails are connected — the state machine accommodates them, `PROMPT.md` §4.

The order inside `payments.transfer` is the one §4 asks for: validate → ownership and currency
guards → balance → limits/policy → Verification-of-Payee → optional step-up → `post_transaction`
→ outbox event. Every step above the arrow can refuse without writing anything.

The three seams that were empty before now carry traffic:

- **Policy** (`StaticLimitPolicy`) returns `allow | deny | require_approval` from a per-payment
  limit, a rolling daily limit, and a step-up threshold. `mandates` exists as an empty collection;
  agent mandates will be evaluated through this same interface.
- **Step-up / SCA** (`DevCodeStepUp`) logs the challenge and accepts one fixed dev code. Anything
  over `PAYMENT_STEP_UP_THRESHOLD_MINOR` (default 1.000,00) goes through it.
- **Verification of Payee** (`InternalPayeeVerifier`) compares the name you typed against the
  account holder's name. `no_match` refuses the payment until the caller re-sends it with
  `acknowledgePayeeMismatch`.

Signing re-checks ownership, account status and balance before posting. A payment approved
yesterday cannot post today against money that is no longer there.

### Accounts appear during onboarding

Completing onboarding opens **RON current, RON savings, EUR savings** and posts
`DEMO_OPENING_BALANCE_MINOR` (default 2.500,00 RON) into the current account from the house
settlement account. It is a real double-entry posting, not a seeded number, which is why it goes
through `payments` — rule 5 says only payments calls the money door.

That is a demo convenience and it is the one place the code does something a bank would not.
Set `DEMO_OPENING_BALANCE_MINOR=0` to open the accounts empty.

Multi-currency is at the schema level only. An account holds exactly one currency and a transfer
must be same-currency; RON→EUR is refused with a clear message. There is no FX in v0.

## The recoverable PIN — a deliberate, documented weakening

"I forgot my PIN" takes username + password, signs the customer in, and shows the PIN on the
welcome screen behind a reveal toggle. A hash cannot do that, so the PIN is stored **twice**:
`pinHash` (Argon2id, what sign-in checks) and `pinEncrypted` (AES-256-GCM, what the reveal
decrypts, with the user id as associated data so a blob cannot be moved between users). This was
chosen knowingly over the alternative — regenerating a fresh PIN — and it means:

- anyone holding both the database and `PIN_ENCRYPTION_KEY` can read every customer's PIN;
- key rotation needs a re-encryption pass that does not exist yet;
- a real bank would reset the PIN instead. This one is a demo with no real funds.

What the implementation does guarantee: the plaintext PIN appears **only** in the HTTP response
body. `CommandResult.sensitive` is merged into the response but never written to the idempotency
store, the audit log, or the outbox. Replaying a stored `Idempotency-Key` therefore returns the
non-secret half only — a replayed reveal does not re-reveal.

The password check in `auth.reveal_pin` is an authentication, so it lands on the same welcome
screen as `auth.sign_in` — and so is `auth.password_reset.complete`, which knows the customer read
a code sent to the address on the account. All three paths end on the welcome screen, the last two
with the PIN panel on it. With no session token yet, "signed in" means exactly that screen; when
sessions arrive, all three mint one.

Accounts created before this feature have no `pinEncrypted`; their reveal fails with a clear
message, and their password reset still succeeds and still signs them in — the welcome screen just
says why there is no PIN to show.

Other tradeoffs worth knowing:

- `POST /auth/password/reset` returns 404 for an unknown username, which allows username
  enumeration. Consistent with a demo that already returns OTP codes in dev-mode responses;
  fix it when the system stops handing out `devCode`.
- PIN and password failures are two separate tracks on the user record (`AuthUser.sign_in` /
  `AuthUser.authorise_reveal` in `backend/auth/credentials.py`), stored as `pin` / `password`
  sub-documents. They do not share a counter or a lockout.
  - **PIN** (`signIn`): after `PIN_MAX_FAILURES` wrong PINs, `pin.locked` is set — no timer, no
    self-reset. Sign-in with PIN is refused until the password is verified once (the "I forgot my
    PIN!" screen), which clears the flag.
  - **Password** (used to reveal the PIN and, later, to reset it): failures escalate through
    fixed tiers — `PASSWORD_MAX_FAILURES` wrong attempts locks it for `PASSWORD_LOCKOUT_SECONDS`;
    one more wrong attempt after that lock expires extends it to
    `PASSWORD_LOCKOUT_EXTENDED_SECONDS`; one more after that sets `status: "locked"`
    permanently — there is no admin back-office in v0, so a permanently locked demo account has no
    self-service recovery, by design. A correct password at any stage before that resets the
    track to zero.

## Personal details come from the ID document

Everything the app shows about who you are is read once, by OCR, from the ID document you upload
in step 1 of onboarding — never typed by hand and never invented. `identity.onboarding.complete`
copies the extracted identity onto the user record as an `identity` sub-document (full name, birth
date, masked CNP, masked document number, document expiry), so the rest of the system has one
source for it:

- **`GET /me`** returns it, alongside the username, email and phone from the contact step. It is
  the read model behind the dashboard's Settings screen, which renders those fields **read-only** —
  a customer cannot retype their own legal name, and there is no endpoint that would let them.
- **The dashboard greeting, the agent dock and the chat** address the customer by the given name
  from the document, not by their username.
- **Accounts** already carried `holderName` from the same extraction; **cards** now emboss it too,
  instead of the uppercased username.

Only the **masked** CNP is copied onto the user record. The raw CNP stays where the OCR put it and
is not spread any further — see the note below about `GET /onboarding/{id}`.

`ops/006_user_identity.js` backfills `identity` for accounts created before this existed, reading
each user's own KYC case, and re-stamps `holderName`/`ownerName` on their accounts and cards. Users
whose KYC case has no extracted document keep `identity: null`; `GET /me` returns null for them and
the Settings screen says so instead of showing blanks.

## Cards — a backend without a session

`backend/cards/` implements the six actions on the dashboard's Cards mockup, through the same one
write path as everything else (`bus.execute` → policy-free for now, audit, outbox, idempotency):

- `POST /cards/virtual` — issue a virtual Mastercard for a user
- `POST /cards/{id}/freeze` / `/unfreeze` — reversible pause
- `POST /cards/{id}/block` — terminal; every other action on that card then fails with
  `illegal_transition`
- `POST /cards/{id}/pin/reveal` — same `CommandResult.sensitive` channel as `auth.reveal_pin`, so a
  replayed `Idempotency-Key` does not re-reveal
- `POST /cards/{id}/details/reveal` — same `sensitive` channel, returns the CVV; the frontend's
  "Show details" button flips the card to its back face to show it. Cards issued before this
  endpoint existed have `cvvEncrypted: null` and reject the call with `illegal_transition`
  (`ops/005_cards_cvv.js` backfills the field as `null`, not required, for exactly that reason)
- `POST /cards/{id}/limits/atm` and `/limits/online` — bigint minor units, bounded in
  `cards/validation.py`
- `GET /cards?username=` — read model, bypasses the bus like `GET /onboarding/{id}` does

"Monthly online spend" has no backend — it stays a static number on the mock, unchanged, as asked.
The date printed on the front of each card is client-side only (the browser's local clock via
`Intl.DateTimeFormat`), not persisted or served by the backend.

There is no session token (see above), so every card endpoint takes `username` in the request body
instead of a bearer token, resolves it to a user id, and checks the card belongs to that user
before doing anything. The `Actor` on each command is `Actor.public_cards()` — a system actor, not
`Actor.user(...)` — exactly like `auth.sign_in` stays on `Actor.public_auth()`; the resolved
`userId` lands in the audit `after`/event `payload` instead. This is a real gap (anyone who knows a
username can manage that user's cards) and not a new one — it is the same gap every existing
endpoint already has. Close it once for all of them when sessions arrive, not per-feature.

Card issuance now embosses the cardholder's name from the ID document (`AuthUser.display_name`,
falling back to the uppercased username for a user with no extracted identity).

The card PIN is 4 digits, generated at issuance and stored only as `pinEncrypted`
(`AesGcmPinCipher`, same key as the account PIN, associated data = card id so a blob cannot move
between cards) — there is no `pinHash`, because nothing ever authenticates *with* a card PIN here.
The CVV is 3 digits, same treatment: generated at issuance, stored only as `cvvEncrypted` with its
own associated data (`card id + ":cvv"`) so a PIN blob and a CVV blob can never be swapped for the
same card even if both were somehow exfiltrated together.
Card numbers are never generated or stored in full: only a random last-4 exists, anywhere, ever —
see `cards/adapters.py`. Keep it that way; a full PAN puts real card-data handling code in a repo
that promises there is none (`PROMPT.md` §0).

New users start with zero cards; there is no seed script yet for a starter set matching the mock's
four cards. `ops/004_cards_schema.js` adds the `cards` collection.

## What the payments screen does not do yet

Present in the interface, deliberately inert, each marked "coming soon" rather than removed
(`PROMPT.md` §4: no dead links):

| Control | Why it is not built |
|---|---|
| Split bill | Not in `PROMPT.md` §4 |
| Scan QR | Not in §4 |
| Read aloud | Text-to-speech is a settings feature; `/settings` is unbuilt |
| Ask GEMS | The entire agent layer is out of scope by §7 |
| Cards filter | Cards are explicitly not in v0 |

The rest of the design archive — dashboard, portfolio, cards, analytics, settings, and the left
navigation rail that carries them — is unbuilt. This release renders the payments screen on its
own chrome; the rail arrives with the second screen that needs it.

Also missing, and worth knowing:

- **Sessions do not refresh.** One opaque token, SHA-256 hashed at rest, TTL from
  `SESSION_TTL_SECONDS`, revoked on sign-out and swept by a Mongo TTL index. No rotation, no
  refresh token, no "remember me". A reload signs you out.
- **The daily limit resets at UTC midnight**, not in the customer's timezone.
- **`GET /payments/transactions` returns one row per journal entry you own**, so a transfer
  between two of your own accounts shows twice — once out, once in. That is the ledger telling
  the truth rather than the UI hiding a leg.
- **No seed script.** `PROMPT.md` §4 asks for one with two demo users and ~30 transactions;
  registering through the wizard is currently the only way to get data.
- **No automated tests.** The invariants in this section were verified by hand against a running
  stack. `PROMPT.md`'s definition of done wants them in `pytest`; they are not there yet.

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
