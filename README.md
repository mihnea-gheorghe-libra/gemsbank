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
After a successful sign in you land on a **dashboard mockup**: a mostly frontend-only prototype
(`frontend/main/dashboard.jsx` and `frontend/components/dashboard-*.jsx`) covering Dashboard,
Payments, AI Assistant, Portfolio, Cards, Analytics and Settings. It is a deliberate, explicitly
approved deviation from `PROMPT.md` §4 — cards, investments, analytics and the chatbot are listed
there as *not in v0* — kept as UI only, with hand-authored demo data
(`frontend/helpers/dashboard-data.js`) for the parts that are not wired to a real backend. The
PIN-reveal screen (`AUTH.PinRevealScreen`) still runs first whenever a flow surfaces the PIN
(forgot-PIN, password reset); its "Close and continue" action opens the dashboard mockup. Plain
PIN sign-in opens it directly, since it has no PIN to show — there is no separate "welcome" screen
any more. Sign-in already mints the session token described above, and the dashboard mockup uses
it: `Home` and `Payments` read real accounts and movements over `Authorization: Bearer …`, the
same way the rest of this section describes.

The **Cards** screen is one exception: it has a real backend (`backend/cards/`) — issue a
virtual card, freeze/unfreeze, reveal PIN, set ATM/online limits, block permanently — but the
Cards screen itself still renders from `dashboard-data.js`, not from these endpoints. See
"Cards — a backend without a session" below before wiring it up.

The **Investments** widget on the Portfolio screen is the other: its prices, history and FX are
real, fetched live through `backend/investments/`. See "Investments — real prices, demo trades"
below.

The mockup's **Payments** screen now moves real money for its core flow, through the same
`backend/payments/` module as the (currently unrendered) standalone `PaymentsPage`:

- **New payment** has two rails, both real. *IBAN transfer* posts a `MakeTransfer` command against
  `/payments/transfers` — it only reaches accounts actually held at GEMS, so a made-up IBAN is
  correctly rejected. *Between my accounts* is a dropdown of the customer's own accounts,
  restricted to targets in the same currency because GEMS does not convert money. A payment above
  the step-up threshold comes back `awaiting_signature`; the dashboard opens a sign dialog
  (dev code from `config.py`, shown inline in demo mode) that calls `/payments/transfers/{id}/sign`.
  Accounts, the movements table and the pending-signatures panel all reload from the server after
  every payment or signature, so what you see matches MongoDB, not stale local state.
- **Templates** are saved payees under a name the customer chooses (Rent, Mum, Gym) — still React
  state, not the real `beneficiaries` collection. They live on the Payments screen — add, edit,
  delete, or *Pay* to open the dialog prefilled — and appear as quick-pick chips inside the dialog.
- **Split bill** is its own button and its own dialog, not a third rail of New payment: a total,
  the account to collect into, a row per person, and *Split equally* which divides in minor units
  and puts the remainder on the first share, so the parts always sum to the total. Open requests
  land in a card on the Payments screen where each share can be marked paid. This stays React
  state only — nothing reaches the ledger, and a refresh resets it.
- **All / Income / Spending / Pending / Cards** and the filter box now actually filter the
  movements table. `Cards` selects card-channel movements; the filter box matches counterparty,
  reference or IBAN.

The **Portfolio** screen mixes the same way:

- **Open new account** picks a type and currency. For **Current** and **Savings** — and now
  **Invest** — it posts `OpenAccount` to `/accounts`, which mints a real GEMS IBAN and writes the
  account to MongoDB; an optional funding amount is a second, real internal transfer through the
  same payments path above (and can itself land in `awaiting_signature`). The new account shows up
  everywhere accounts are listed, including the payment dropdowns. **Term deposit** and **Savings
  goal** still create React-state-only products, since deposits are not a v0 concept on the ledger.
- **New deposit** opens a term deposit or a savings goal with a target — React state only. Term
  rates come from `depositTerms`; the money leaves the funding account (a real account, debited
  only in local state) and the maturity date is computed from the term. Every product can be
  topped up, withdrawn from, or closed — closing returns the balance to an account in the same
  currency, again only in local state.
- **Investments** buy and sell holdings at the stored unit price, spending *cash to invest* before
  touching an account, exactly as `PROMPT.md` requires — no command, no journal entry, no outbox
  event for a trade. *Cash to invest* itself is real, though: it is the balance of the customer's
  `invest`-kind account, read the same way as any other account. A customer with no investment
  account sees an **"Open an investment account"** button in its place instead of an invented
  number. Position value is derived from units times price, so the INVESTMENTS header always
  equals the sum of what is listed under it.
- **Apply for credit** records an application against a product from `creditProducts` (with its
  rate and maximum) and leaves it in `review`. **Nothing is approved here.** The eligibility
  decision is the seam left for a future agent that reads accounts and income; until that agent
  exists, applications sit in review and say so on screen. React state only.

The Dashboard home screen's quick actions split the same way. **Add funds** is a mock top-up —
React state only, chosen deliberately over a real house-treasury deposit so it stays an obvious
sandbox action, not something that reads as a real funding rail. **Exchange** is real: see
"Exchange — real currency conversion" below.

Balances and amounts in the mockup are integer minor units, formatted for display, so the
arithmetic above matches rule 1 even though no money is real. Interest rates are integer basis
points for the same reason.

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
  investments/       market data only — read-only, no money movement
    instrument.py    Instrument, Quote, HistoryPoint, ExchangeRate, MarketSnapshot
    service.py       catalogue reads, TTL cache, last-known-good fallback, FX conversion
    validation.py    minor-unit and rate conversion, history range whitelist
    adapters.py      Yahoo chart client, Frankfurter rate client, shared httpx transport
  payments/
    service.py       commands, ports, handlers, read models
    payment.py       the Payment state machine and the Beneficiary aggregate
    validation.py    reference, counterparty, category, cursor codec
    adapters.py      clock, limit policy, step-up stub, Verification-of-Payee stub
  capabilities/      SEAM 6: the registry an agent layer reads its tool list from
    registry.py      Capability, SideEffect, the in-memory CapabilityRegistry
    service.py       the registered capabilities — name, in/out schema, resolver, scope
    support_docs.py  parses frontend/help.html into searchable FAQ/guide entries
    analytics.py     the four analytics.* resolvers
    payments.py      balances, beneficiaries, and the money-moving transfer *proposal*
  agents/            the workers — narrow callers of capabilities/, never of bus.execute
    adapters.py      AzureChatCompleter — Azure OpenAI, tool-calling
    base.py          ToolCallingAgent — the shared loop: capability-only, audits every run
    support.py       SupportAgent — read-only, FAQ/guide + own profile/sessions, tool-scoped
    analytics.py     AnalyticsAgent — read-only, forecasts and month-over-month explanations
    payments.py      PaymentsAgent — balances (read) + transfer proposals (money-moving)
    orchestrator.py  the lead agent: routes, fans out, aggregates; holds no capabilities
    transcript.py    sanitises the client-supplied conversation history
    service.py       wraps the actor as kind="agent", on_behalf_of=user_id
    analytics_service.py / payments_service.py   the same wrapping, per worker
  escalations/       handing a conversation to a human
    handoff.py       the Handoff aggregate
    service.py       RequestHandoff — a normal command through bus.execute
    validation.py    question and reason bounds
  helpers/
    context.py       ids, Actor, correlation id, JSON logging
    crypto.py        Argon2id hasher, AES-GCM PIN cipher
    errors.py        error taxonomy → HTTP status

frontend/            no build step; index.html script order is the module graph
  index.html
  main/app.jsx       chooses sign in vs register, mounts the app
  main/signin.jsx    sign in, PIN recovery, password reset, welcome, hands off to the dashboard
  main/register.jsx  onboarding page state and flow orchestration
  main/dashboard.jsx post-login dashboard mockup: screen state, chat state, accounts,
                     transactions, templates and split bills, mock-data wiring
  components/        ui.jsx (primitives) · rails.jsx (step rail, agent panel) · steps.jsx ·
                     auth.jsx (sign-in forms, PIN panel, welcome) ·
                     dashboard-widgets.jsx (segmented control, bars, donut, progress, amount,
                     minor-unit format/parse/split helpers) ·
                     dashboard-shell.jsx (sidebar, topbar, agent dock, new-payment, split-bill
                     and template dialogs) ·
                     dashboard-portfolio.jsx (open-account, deposit, invest and credit dialogs,
                     IBAN/rate/unit helpers) ·
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

Nothing writes outside this path. `backend/agents/` is a first, read-only caller of the *read*
side of the platform (`backend/capabilities/`, not `bus.execute`) — see "Agents" below. No agent
calls `bus.execute` yet; when one does, it becomes a second *caller* of it, never a second pathway.

`CommandResult` has two output channels: `data` is stored and replayed under the idempotency key;
`sensitive` is merged into the HTTP response and never persisted anywhere. Use `sensitive` for
anything a replay must not hand out twice.

Failed authentication is the one place a handler writes outside the command transaction: the
attempt counter is saved with no session before the error propagates, because the rollback would
otherwise erase the evidence of the failure. `onboarding` does the same for OTP attempts.

## How money moves

One collection, `journalTransactions`, holds the whole ledger. Each document is one transaction
in one currency with an embedded `entries` array, and it is written by exactly one function —
`ledger.post_transaction`. Two callers reach it, both explicitly approved: `payments` (transfers,
opening deposits) and `exchange` (currency conversion) — see "Exchange — real currency conversion"
below for why a second caller was let in, and how it still keeps every transaction single-currency.

Entry amounts are **signed integer minor units, from the account holder's point of view**: the
account that receives gets `+`, the account that pays gets `−`. A customer balance is therefore
the plain sum of that account's entries, and it is always derived — there is no balance column
anywhere. House accounts (`house:settlement:RON`, `house:fee_revenue:*`, `house:suspense:*`,
`house:fx:*`) are chart-of-accounts constants, not rows in `accounts`; the settlement account
carries the negative counter-leg of every demo deposit, and `house:fx:{currency}` carries the
negative counter-leg of every currency exchange.

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
through `payments` — rule 5 names the callers of the money door, and onboarding is not one of them.

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

## Investments — real prices, demo trades

`backend/investments/` is the only feature that reaches outside the system. It is **read-only**:
no command, no journal entry, no outbox event. Buy and Sell on the Portfolio screen still move
React state only, exactly as before — the money door is untouched.

Two public providers, neither needing a key or an account:

- **Yahoo Finance** `v8/finance/chart/{symbol}` — an unofficial endpoint — for `URTH`
  (MSCI World ETF, USD), `TLV.RO` (Banca Transilvania on BVB, RON) and `BTC-USD`. One provider
  covers all three asset classes. It returns the spot price and a daily close series.
- **Frankfurter** for USD→RON, both the latest rate and a daily time series, sourced from ECB
  reference rates.

Everything is normalised to **RON minor units** before it leaves the service. Floats exist only
inside `adapters.py`; `validation.py` converts them with `Decimal` and `ROUND_HALF_EVEN`. FX rates
cross the wire as `rateMicro` — the rate scaled by 1e6 — never as a float.

Historical points are converted with the FX rate **of that day**, not today's, so the RON curve
has the right shape and not just the right endpoint. Weekends and holidays forward-fill from the
last published rate.

- `GET /investments/instruments` — the static catalogue
- `GET /investments/market?range=6mo` — quotes, day change in bps, converted history, FX rates
- `GET /investments/market?refresh=true` — what the widget's Refresh button calls; skips the TTL
  cache and refetches, with a floor of `investments_min_refresh_seconds` so a held-down button
  cannot hammer an unofficial endpoint

**When a provider is down** the service degrades in three steps: the TTL cache
(`investments_quote_ttl_seconds`, 15 min), then the last successful response held in memory, then
the fallback prices baked into `adapters.py`. The response carries `live: false` and the widget
says so, with the timestamp of the data it is actually showing. Retries back off to
`investments_retry_seconds`. The app therefore starts and renders with no internet at all.

The cache is per-process and in memory: a restart loses the last-known-good and falls back to the
baked-in prices until the first successful fetch.

`Instrument.id` values (`h-msci`, `h-tlv`, `h-btc`) match the holding ids in `dashboard-data.js`;
that join is what lets the mockup's unit counts meet real prices.

## Exchange — real currency conversion

`backend/exchange/` is a small feature folder — `service.py`, `validation.py`, `adapters.py`, no
aggregate file, because there is no new persisted entity: a conversion is two correlated,
single-currency journal transactions, not a thing of its own. It is a deliberate, explicitly
requested and approved deviation from `PROMPT.md` §4 ("No FX conversion in v0") — see the note
there for the reasoning and how it keeps rule 2 intact.

The **Exchange** quick action on the Dashboard home screen opens a dialog: pick a RON account,
pick EUR or USD, enter an amount. The rate comes live from Frankfurter (`GET /exchange/rate`, the
same free, keyless ECB-backed API `backend/investments/` uses, fetched independently — the two
features do not share a client, a small accepted duplication rather than a cross-feature import).
`POST /exchange/convert` runs the `ConvertCurrency` command through `bus.execute`, same as every
other write: idempotent, audited, one outbox event.

A conversion posts **two** `fx_conversion` journal transactions in the same DB transaction, tied
by one `correlation_id`:

1. `-amount` from the source account, `+amount` into `house:fx:{sourceCurrency}`.
2. `-convertedAmount` from `house:fx:{targetCurrency}`, `+convertedAmount` into the target account.

Each transaction is balanced and single-currency on its own — the `journalTransactions` Mongo
validator still enforces "sums to zero" per document, unchanged. The `house:fx` accounts are a
demo treasury exactly like `house:settlement` (the source of the onboarding opening balance): not
real `Account` documents, never balance-checked, free to run arbitrarily negative in every
currency it hands out. If the customer has no account in the target currency yet, one is opened
for them automatically (a real `current` account, real IBAN) before the conversion posts — the
same `AccountsService.open_account` the "Open new account" flow uses.

There is no step-up here yet — unlike payments, a conversion always posts immediately, whatever
the amount. That is a scope cut for a first version, not a design decision; adding the same
`StaticLimitPolicy` / signature dance payments uses would be straightforward if this needs to
handle larger amounts later.

`payments.transfer` is unaffected: `guard_same_currency` still blocks a payment between two
accounts that don't share a currency. Exchange is the one sanctioned place an account's currency
boundary is crossed, and it does that as two single-currency postings, never a mixed-currency
journal entry.

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

`backend/cards/` implements the actions behind the dashboard's Cards screen, through the same one
write path as everything else (`bus.execute` → policy-free for now, audit, outbox, idempotency):

- `POST /cards/virtual` — issue a virtual Mastercard for a user
- `POST /cards/physical` — issue a physical Visa debit card for a user; same handler shape as
  virtual (`CardsService._issue`), only `kind` and validity period differ (3 years virtual, 5
  physical). The frontend's "Issue card" button opens a dialog to choose between the two.
- `POST /cards/{id}/freeze` / `/unfreeze` — reversible pause
- `POST /cards/{id}/block` — terminal; every other action on that card then fails with
  `illegal_transition`. The frontend labels this **"Delete card"** and, once blocked, drops the
  card from the visible grid — its masked number moves to a "History" dialog instead. Nothing is
  deleted from Mongo; this is a UI relabelling of the existing terminal transition, chosen over
  adding a second terminal state, consistent with the rest of the app never hard-deleting state.
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

The card **back face** (`SCR.CardsScreen` in `dashboard-screens.jsx`) shows the number, expiry and
CVV stacked, same font/size, nothing else. The number shown there is a **client-side-only cosmetic
mock** (`mockFullNumber`, deterministic from the card id) — never sent to or stored by the backend,
which still never generates or keeps a full PAN (`cards/adapters.py`, unchanged, see below). A
frozen card gets a translucent blue veil over the whole tile, front or back
(`--color-info`, added to `frontend/styles/tokens.css` for this — the extracted design archive has
no blue; `PROMPT.md` §3's fidelity rule says structure wins where the archive and the brief
disagree, logged here per that rule). A Mastercard-kind card's front shows a small two-circle
network mark bottom-right, drawn in the app's own plum/lime tokens rather than the real trademarked
mark (colours, shape and IP are Mastercard's, not ours to reproduce).

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

## Agents — a first, narrow caller past the §4 boundary

`PROMPT.md` §4 lists "the entire agent layer" as explicitly not in v0, and §7 says to design it in
docs, build none of it. `backend/capabilities/` and `backend/agents/` are a **deliberate, explicitly
approved deviation** from that — two read-only workers, not a reinterpretation of the boundary. The
rest of v0 (identity, ledger, payments, cards) is unaffected: neither module is on the money path,
and both `SupportService` and `AnalyticsService` are constructed lazily, not at startup, so a clone
without Azure OpenAI credentials still boots and runs everything else — only the two `POST
/agents/*/ask` routes fail.

`backend/capabilities/` (SEAM 6) is the registry §7.6 describes: a `Capability` is a name, a
Pydantic input/output schema, a `SideEffect` (`read` / `write` / `money-moving`) and a resolver
function. Eight are registered, all `SideEffect.READ`. Four back `SupportAgent`: `support.faq.search`
(a small regex parser, `backend/capabilities/support_docs.py`, that reads `frontend/help.html`
itself, so the FAQ/user guide has one source of truth instead of a copy that can drift),
`settings.profile.get`, `settings.preferences.get` (the user's own `lang`/`theme`, already persisted
on the user document — no new storage) and `settings.sessions.list` (thin wrappers over
`AuthService.get_me` / `list_sessions`). `settings.security.get` (2FA/passkeys/PIN-changed-at) was
considered and deliberately skipped: none of that state exists in the backend today — 2FA and
passkey counts are hardcoded display strings in `frontend/components/dashboard-screens.jsx`, and no
PIN-change timestamp is stored anywhere — so building it would mean either the agent fabricating
security status or a real data-model change (new fields + migration), neither of which belongs in a
capability add.

The other four (`backend/capabilities/analytics.py`) back `AnalyticsAgent`, and turn transaction
history into forecasts and explanations — the "fact vs. narrative" split is structural, not a prompt
convention: every output schema carries a `status` (`"ok"` or a tool-specific sentinel —
`insufficient_data`, `no_goal_found`, `no_activity`, per-category `no_clear_cause`), and when status
isn't `"ok"` the rest of the fields stay empty, so the model narrates the sentinel instead of
papering over a gap with a guessed number.
- `analytics.cashflow_forecast.get` projects the balance forward from **confirmed recurring**
  income/payments only — never variable spending or market prediction. "Confirmed recurring" is a
  concrete, code-level definition (no such detector existed before this): ≥3 occurrences of the same
  counterparty+category in a 6-month lookback, 24–40 days apart, amounts within ±15% of the group's
  median. Zero qualifying groups → `insufficient_data`, not a silent best-effort guess.
- `analytics.goal_gap.get` compares a savings goal's required monthly rate against the actual net
  rate observed on its linked account over the last 3 months. Backed by a new minimal feature,
  `backend/goals/` (below) — no goal set → `no_goal_found`.
- `analytics.month_recap.get` and `analytics.what_changed.get` return facts only (biggest expense,
  busiest day, category deltas, per-category cause of a spend change — `new_merchant` /
  `increased_frequency` / `increased_price` / `no_clear_cause`), never prose; the agent's prompt
  does the narrating, so the numbers stay testable and localizable independent of phrasing.

All four page through the existing `PaymentsService.list_transactions` cursor (already sorted
newest-first) and stop once a page crosses the requested date boundary
(`capabilities/analytics.py::_transactions_in_range`) — no date-range parameter was added to
`payments/` or `ledger/` for this; that boundary stayed untouched on purpose. All four are also
scoped to RON transactions/accounts only: mixing currencies into one sum would be silently wrong,
and multi-currency forecasting was never asked for — an explicit v0 cut, not an oversight.
`GET /capabilities` describes all eight alongside the write-side command list.

**`backend/goals/`** exists only so `analytics.goal_gap.get` has real data to read — it followed
the same shape check as every other feature (aggregate, `service.py`, `validation.py`) and the same
one-write-path rule (`POST /goals` → `bus.execute(CreateGoal(...))`, `backend/goals/service.py`,
migration `ops/008_goals_schema.js`). v0 is **one active goal per user**, enforced by a unique Mongo
index on `userId`, not just application code — no listing, editing or closing endpoints, because
nothing past `goal_gap` needs them yet.

`backend/agents/` has three workers and an orchestrator (see below). `SupportAgent` — answers from the
FAQ/user guide and can look up the signed-in user's own profile, preferences, or active sessions,
for account-settings questions (`POST /agents/support/ask`). Two prompt-level behaviours worth
knowing: it cites the FAQ/guide section a `support.faq.search` answer came from, and it keeps a
content gap ("not in the FAQ") and a scope limit ("not in the sixth capability I have — try
Cards/Payments/Home") in distinct, non-interchangeable wording, pointing to the right screen for
the latter instead of a bare refusal. Both are prompt instructions, not new code paths — no intent
classifier, same allow-list enforcement. It is a thin subclass of
`backend/agents/base.py::ToolCallingAgent`, which holds the actual tool-calling loop against Azure
OpenAI. The subclass supplies only a system prompt and a `tool_names` allow-list; `ToolCallingAgent`
refuses — in code, before the call happens — any capability not in that allow-list or not
`SideEffect.READ`, per §7's hard rule 1. The allow-list is load-bearing, not decorative:
`backend/tests/test_support_agent_scoping.py` builds a fake registry that also holds a
money-moving capability and asserts `SupportAgent` never offers it to the model and refuses to call
it if asked to anyway. `ToolCallingAgent` was built as a shared base, not inlined into
`SupportAgent`, precisely so the next worker doesn't have to copy the loop again. Three things
worth knowing:

- **The calling actor is `kind="agent"`, not `kind="user"`.** The route wraps the signed-in user
  as `Actor(kind="agent", id="support-agent", on_behalf_of=user_id)` before handing it to the
  agent — the first real use of `on_behalf_of` (§7.1). Capability resolvers read
  `actor.subject_id()` (`on_behalf_of or id`) rather than `actor.id`, so they scope correctly to
  the human whether the caller is a user or an agent acting for one.
- **Prompt injection is assumed, not handled by the prompt.** The system prompt tells the model
  that tool results are data, not instructions — but the actual enforcement is the tool-scope and
  `SideEffect.READ` checks inside `ToolCallingAgent.ask`, in code, not the model choosing to comply
  (§7's hard rule 5). There is no mandate system yet, so `SupportAgent` cannot be given a
  money-moving capability to call, and it cannot see accounts, balances, cards or transactions —
  only its own four capabilities.
- **Every run is audited** (§7.4/§7.7), not just logged. Each capability call writes an
  `audit_log` record (`capability.<name>`, `entityType: "capability"`) and the final answer writes
  one more (`agents.support.answered`, `entityType: "agent_run"`) — sharing a `runId` and the
  request's `correlationId`, so one agent-initiated answer is fully reconstructable from
  `auditLog` alone, the same way a payment is. `backend/tests/test_tool_calling_agent.py` verifies
  the linkage with a fake audit recorder — no live Mongo needed for that test.
- **Rate-limited per user, in-process.** `AgentRateLimiter` (`backend/agents/service.py`) is a
  sliding-window counter over `settings.agent_rate_limit_max_calls` /
  `agent_rate_limit_window_seconds` (defaults: 20 calls/hour), keyed by the signed-in user's id,
  checked in `SupportService.ask` before the agent runs. It is in-memory on purpose — no new Mongo
  collection for a single-process demo — so it resets on restart and does not coordinate across
  API instances; raises the existing `RateLimitedError` (429), no new error type or route code.

`AnalyticsAgent` (`backend/agents/analytics.py`, `POST /agents/analytics/ask`) is the second
worker, built the same way: a thin `ToolCallingAgent` subclass supplying only a system prompt and
its `tool_names` allow-list (the four `analytics.*` capabilities above), same `AgentRateLimiter`
class reused with its own instance (`backend/agents/analytics_service.py::AnalyticsService`), same
audited-run-per-`run_id` guarantee, same in-code allow-list/`SideEffect.READ` enforcement — nothing
about the second worker changed how `ToolCallingAgent` works, which is the point of it being a
shared base. Its prompt carries one stake-appropriate addition beyond `SupportAgent`'s: every
number it says must come from a tool result, full stop, and any forecast or "capping X would help"
framing must be said as an estimate, not a certainty — financial projections, not FAQ answers.
`backend/tests/test_analytics_agent_scoping.py` mirrors `test_support_agent_scoping.py`'s allow-list
proof; `backend/tests/test_analytics_capabilities.py` exercises the four resolvers' actual logic
(recurring-pattern detection, the goal-gap rate math, the category-cause classifier) against a
scripted `PaymentsService`, no Mongo. **No frontend wiring was added for it** — the task asked for
the tools, not a second chat surface; when one is built, it should reuse the `aiGenerated`/
"always double-check" disclaimer mechanism already in `dashboard.jsx`, not invent a new one,
especially for a worker whose whole job is projections and recommendations.

The frontend's "Ask GEMS" dock and the chat screen's free-text box (`frontend/main/dashboard.jsx`)
call `SupportAgent` for whatever the user types — busy state, error fallback, and an
"AI-generated" disclaimer under real answers. The dock's *suggested-prompt buttons* (per-screen
shortcuts like "How do I freeze my card?") still answer from `dashboard-data.js`, unchanged: most
of them ask about spend, cards, portfolio or payments, and `SupportAgent` has no tool for any of
that — it would either say so (correctly) or, worse, dig through the FAQ for something that isn't
there.

### Running the tests

`pytest` from the repo root is the whole suite. `pytest.ini` there sets `testpaths = tests
backend/tests`, so both roots run in one command and the stray `test_azure.py` at the root (a
manual Azure smoke script, not a test) is never collected. `cd backend && pytest` still works and
uses `backend/pytest.ini`. You need the test dependencies once: `pip install -r
backend/requirements.txt` — `pytest-asyncio` is what makes the `async def` tests run at all, and
without it they do not fail, they *error at collection*, which reads like something much worse.

The suite is **hermetic on purpose**. `backend/config.py` has nine settings with no defaults, so
merely importing it outside Docker used to blow up collection for every agent test.
`backend/tests/conftest.py` pins those nine plus every value the suite actually asserts on — the
payment per-transaction, daily and step-up limits above all — so a developer's `.env` cannot change
a test result, and `WEB_DIR` is resolved to whichever directory really holds `help.html` (the
checkout's `frontend/` locally, the `/web` mount inside the container). The root `conftest.py`
loads that same file first, so the pinning happens before anything can import `backend.config`.
`backend/tests/test_the_suite_is_hermetic.py` asserts all of this, and is the test that fails first
if someone reintroduces a dependency on ambient configuration.

Verified green three ways — `pytest` from the repo root, `pytest` from `backend/`, and inside the
`api` container — and every test file also passes run on its own, so nothing depends on collection
order.

The default run (`addopts = -m "not live_llm"`) is deterministic and free: harness-level guarantees like allow-list
enforcement, the `MAX_TOOL_ROUNDS` giving-up path, and the rate limiter, all against a scripted
fake chat completer, no network. `backend/tests/test_support_agent_live_eval.py` is marked
`live_llm` and skipped by default — it calls the real Azure OpenAI deployment through
`get_support_service()` / `get_analytics_service()` to grade prompt quality (injection resistance,
FAQ-gap vs. scope-limit wording, correct screen fallback, and — for `AnalyticsAgent` — that a
`no_goal_found`/sentinel status gets narrated honestly instead of papered over) that a scripted chat
can't exercise. Run it deliberately after a prompt or model change: `pytest -m live_llm` (needs
`docker compose up`/Mongo and valid `AZURE_OPENAI_*` credentials; set `EVAL_SUPPORT_USER_ID` /
`EVAL_ANALYTICS_USER_ID` to real demo user ids to also cover the cases that need seeded data).

### PaymentsAgent — the first worker that can touch money, and still cannot move it

`PaymentsAgent` (`backend/agents/payments.py`, `POST /agents/payments/ask`) is the third worker and
the first to hold a capability that is not `SideEffect.READ`. It does two things.

**Balances.** `payments.balances.get` answers "how much is in each account", "how much do I have in
total", and "how much is in *that* one". One capability covers all three: with no `accountRef` it
returns every account plus per-currency totals; with an `accountRef` it returns the one account the
customer named, and still returns the totals. The reference is matched the way people actually
speak — a label, a kind (`current`, `savings`, `economii`), a currency in words (`euro`, `lei`,
`dolari`), or the last digits of an IBAN — in `capabilities/payments.py::_match_score`. Two rules
in that matcher matter: naming **both** a kind and a currency ("ron savings") pins exactly one
account or returns nothing, and any reference matching more than one account returns
`status: "ambiguous"` with the candidates rather than picking one. The agent asks; it never guesses
which account you meant.

**Amounts never reach the model as raw integers.** Every balance and total carries a
`balanceFormatted` / `totalFormatted` string ("2.350,00 RON"), and the prompt tells the model to
quote it verbatim. This is deliberate: the prompt also forbids the model from doing arithmetic, so
without a preformatted string it correctly refuses to divide by 100 and reports minor units at the
customer ("952 EUR minor units" — observed, before the field was added). `format_minor` in
`capabilities/payments.py` is the one place that formatting happens server-side; `<Money>`/
`DASH.formatMinor` still owns it in the browser (`PROMPT.md` §6).

**Proposals, never payments.** `payments.transfer.propose` is registered
`SideEffect.MONEY_MOVING` and **writes nothing**: no command, no journal transaction, no payment
document, no outbox event. It re-runs the same read-only guards the real handler runs — ownership,
account status, same-currency, sufficient balance, and `StaticLimitPolicy` against the same
per-transaction / daily / step-up thresholds, counting today's spend the same way
`PaymentsService._spent_today` does — and returns one of three statuses: `proposed`,
`blocked` (with typed `blockers`), or `needs_clarification` (with `candidates`). A `proposed`
result carries `requiresHumanConfirmation: true` and `autoApprovalEligible: false`
(`autoApprovalReason: "no_mandate"`). The customer confirms it on screen, and the confirmation goes
through `POST /payments/transfers` — `bus.execute` — exactly like a hand-typed payment. §7's hard
rule 2 is therefore satisfied in its "returns a proposal + explicit human confirmation" half; the
"in-mandate auto-approval" half is not built, because `mandates` is still an empty collection and
building it is a data-model change nobody has asked for yet.

`ToolCallingAgent` grew a second allow-list, `proposal_tool_names`, to carry this. The existing
guarantee is unchanged and re-asserted in tests: a name in `tool_names` must be `READ`, a name in
`proposal_tool_names` must be `MONEY_MOVING`, and anything else is refused before the resolver
runs. `SupportAgent` and `AnalyticsAgent` pass an empty `proposal_tool_names`, so neither can be
handed a money-moving capability even by mistake.

One behaviour changed for all three workers. The loop used to raise on *any* tool name it did not
recognise, which killed the whole conversation when the model simply mis-typed one — observed live:
gpt-5-mini called `transfer.propose` instead of `payments.transfer.propose` and the customer got a
422. Now the two cases are separated. A name that is **not registered at all** is an ordinary model
slip: the loop feeds back a `no_such_capability` tool result listing the exact valid names and lets
the model correct itself, bounded by `MAX_TOOL_ROUNDS`. A name that **is** registered but sits
outside this agent's grant is a security signal and still raises, as before — that is what
`test_support_agent_scoping.py` has always asserted, and it still does. Malformed tool arguments
are handled the same forgiving way as a mis-typed name.

`backend/tests/test_payments_agent_proposes_but_never_pays.py` is the proof: a `FakeLedger` whose
`post_transaction` raises on contact, asserted across the clean, insufficient-funds, cross-currency,
over-limit and over-daily-limit paths; the ambiguity and formatting rules; and the two refusal
contracts above. Verified against the live stack as well — five real questions through the real
deployment left `journalTransactions`, `payments` and `outbox` at a delta of exactly zero.

The frontend routes the chat to `PaymentsAgent` from the Home and Payments screens
(`agentForScreen` in `frontend/main/dashboard.jsx`); Analytics still routes to `AnalyticsAgent` and
everything else to `SupportAgent`. A `proposed` result renders as a `kind: "proposal"` message — a
card showing the formatted amount, payee, masked IBANs, reference and what is left afterwards, with
copy that says nothing has been sent. Its one button opens the ordinary New-payment dialog
prefilled, so the money still moves through the same screen, the same command and the same
step-up dance as any other payment. The old hardcoded `kind: "tx"` mock card is untouched and still
belongs to the suggested-prompt buttons.

### The orchestrator

`POST /agents/ask` is now the only chat endpoint the frontend calls. `backend/agents/orchestrator.py`
holds an `Orchestrator` that is deliberately **not** a `ToolCallingAgent` subclass and is handed no
`CapabilityRegistry` at all — its only tools are the three workers plus `escalate_to_human`. It
cannot read a balance, resolve an IBAN or touch Mongo even by accident, which is §7's "never calls
the DB" enforced by construction rather than by prompt.

Routing is **delegate-to-one, fan-out-when-needed**. One LLM call classifies the question and
rewrites it to stand alone; if a single worker is chosen its answer is returned verbatim, so the
common case costs two LLM calls, not three. Only a genuinely cross-domain question ("can I afford
to send 200 lei to my savings this month" needs balances *and* spending history) fans out — in
parallel, via `asyncio.gather`, read-only workers only — and pays for a second aggregating call.
The aggregator is given the workers' text and no tools, and is told to copy every figure exactly
rather than recompute it, because it is the one place a number could be silently re-rounded.

The screen you are on is passed as a **hint**, not a decision. `agentForScreen` is gone: the old
five-line frontend router is what sent "how do I freeze my card?" to `PaymentsAgent`.

Multi-turn conversation now works. The transcript travels with the request from the client, which
matches the existing session model exactly — a reload already signs you out, so server-side history
would outlive its own session — and needs no new collection. It is treated as untrusted input:
`backend/agents/transcript.py` drops anything that is not a `user`/`assistant` turn (a forged
`system` turn cannot get through), caps it at 10 turns and 1200 characters each, and never lets it
start on a dangling assistant reply. A forged transcript cannot widen access anyway — the actor
comes from the bearer token and the per-worker allow-lists are enforced in code.

Rate limiting is **per orchestrator run**, keyed `orchestrator:{userId}`: one customer question is
one unit whether it fans out to one worker or three. The orchestrator holds the three agents
directly rather than their services, which is what stops the per-worker limiters from
double-counting.

Escalation to a human is a first-class, always-visible option (§7's hard rule 4), and the workers
did not have to change to get it. The orchestrator can *offer* a human — for fraud, a lost card,
distress, or anything no worker covers — but it never files anything: `escalate_to_human` only
sets a flag on the response. The **customer** files the request, by clicking "Talk to a person",
which runs `RequestHandoff` through `bus.execute` like every other write — idempotent, audited,
one outbox event, into `supportHandoffs` (`ops/010_support_handoffs.js`). No agent ever gained a
write pathway. The internal escalation *reason* is stored on the handoff and shown to staff; the
customer sees a plain localised sentence, never the third-person text the model wrote for the
handover.

Every worker in a run inherits the orchestrator's `run_id` and the request's `correlation_id`, so
a fanned-out answer is still one reconstructable trace in `auditLog`, alongside one
`agents.orchestrator.answered` row naming which workers ran and whether it escalated. A worker that
throws is logged and dropped from the aggregate rather than taking the whole answer down.

`backend/tests/test_orchestrator_routes_without_touching_data.py` covers all of it against a
scripted chat completer — no network: single-worker vs. fan-out call counts, duplicate and unknown
worker names, a failing worker, escalation with and without a worker, proposal pass-through,
`on_behalf_of` propagation, shared `run_id`, screen-as-hint, and every transcript-sanitising rule.

Verified live end to end: "how much do I have" → payments; "how do I freeze my card?" → support
(the case the old router got wrong); "why was my spending higher last month?" → analytics; "can I
afford to send 200 lei to my savings?" → payments + analytics fanned out and merged; "I lost my
card and someone is using it" → escalated with no worker forced; and "and the current one?" with
two turns of history resolved to the right account. Zero movement in `journalTransactions` or
`payments` across all of it.

Not done: no mandates, no `settings.security.get` (see above), no
UI for `AnalyticsAgent`, no multi-goal support. `PaymentsAgent` cannot see transactions, cards or
settings, and `payments.transactions.list` is still not in the registry — add it there, not as a
new pathway, when a worker needs it. The proposal is stateless: `proposalId` is a display string,
nothing persists it, and the confirmation step re-validates from scratch rather than trusting it.

## What the payments screen does not do yet

Present in the interface, deliberately inert, each marked "coming soon" rather than removed
(`PROMPT.md` §4: no dead links):

| Control | Why it is not built |
|---|---|
| Split bill | Not in `PROMPT.md` §4 |
| Scan QR | Not in §4 |
| Read aloud | Text-to-speech is a settings feature; `/settings` is unbuilt |
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
- **Automated tests are thin.** `pytest` from the repo root is green and needs no Docker, Mongo or
  network, but it covers the capability registry, the agent layer and the CNP parser — not the
  money core. The invariants in this section — unbalanced-transaction rejection, idempotent replay,
  insufficient-balance refusal, concurrent transfers, boundary violations — are still only verified
  by hand against a running stack; `PROMPT.md`'s definition of done wants those in `pytest` too,
  and they are not there yet. `backend/tests/test_payments_agent_proposes_but_never_pays.py` is the
  closest thing so far, and it only proves the *agent* cannot move money, not that the ledger is
  right.

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
