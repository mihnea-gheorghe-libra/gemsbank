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
Payments, AI Assistant, Portfolio, Cards, Analytics, Financial education and Settings. It is a
deliberate, explicitly approved deviation from `PROMPT.md` §4 — cards, investments, analytics and
the chatbot are listed
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
real, fetched live through `backend/investments/`, and so are Buy and Sell — see
"Investments — real prices, real trades" below.

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

The **Portfolio** screen (nav key `accounts`, i18n-labeled "Portfolio") is now real end to end —
accounts, term deposits, savings goals and credit applications all read from and write to MongoDB
through the one write path. It used to mix real accounts with React-state-only deposit and credit
mocks; that mock data is gone, replaced by two small new feature folders (`backend/deposits/` and
`backend/credits/`) shaped exactly like `backend/goals/` below:

- **Open new account** picks a type, a currency, and an optional **name** — a plain `label` on the
  `Account` aggregate (it already existed for the auto-generated default; the dialog just lets the
  customer override it now). For **Current**, **Savings** and **Invest** it posts `OpenAccount` to
  `/accounts`, which mints a real GEMS IBAN and writes the account to MongoDB; an optional funding
  amount is a second, real internal transfer through the same payments path above (and can itself
  land in `awaiting_signature`). The new account shows up everywhere accounts are listed, including
  the payment dropdowns. **Term deposit** now opens a real account too (see below); **Savings
  goal** is created from its own card rather than this dialog (see below).
- **Term deposits** (`backend/deposits/`) open a real `savings`-kind pot account — same shape as a
  goal's pot — funded by a real transfer from a chosen account of the customer's, at a rate looked
  up server-side from `products.catalogue.DEPOSIT_PRODUCTS["term"]` by the term in months (the
  client cannot submit a rate). Top-up and withdraw are real transfers between the pot and its
  parent account (`LedgerService.transfer`, the same door `payments` and `goals` already use — not
  a new caller of `post_transaction`). Closing sweeps any balance back to the parent and closes the
  pot account, same as a goal. Unlike goals, a customer can hold **several** term deposits at once,
  and a deposit can be **closed anytime** — no early-withdrawal penalty is modeled, a deliberate
  demo simplification.
- **Savings goal** is unchanged and was already real (see "Agents" below for `backend/goals/`) —
  the Portfolio screen now simply surfaces the same `GoalProgressCard` component the Analytics and
  Education screens already used, instead of duplicating goal creation in the Open Account dialog.
  GEMS still supports one *active* goal per customer at a time.
- **Investments** buy and sell holdings for real, at the live unit price. Every trade runs
  `BuyInstrument` / `SellInstrument` through `bus.execute` — idempotent, audited, one outbox event
  — exactly like every other write in this system. A customer with no `invest`-kind account cannot
  reach the screen's trading actions at all: they see an **"Open an investment account"** button
  instead, and the API refuses the trade regardless (`require_investment_account` at the route,
  the command handler's own ownership-and-kind check underneath it — the real enforcement
  boundary). Position value is derived from units times price, so the INVESTMENTS header always
  equals the sum of what is listed under it. See "Investments — real prices, real trades" below
  for the money mechanics.
- **Apply for credit** (`backend/credits/`) records a real `CreditApplication` against a product
  from `products.catalogue.CREDIT_PRODUCTS` (amount and term validated against it server-side) and
  leaves it in `review`, persisted in MongoDB — it survives a refresh, unlike the old mock.
  **Nothing is approved here.** The eligibility decision is still the seam left for a future agent
  that reads accounts and income; until that agent exists, applications sit in `review` and say so
  on screen. Withdrawing an application is a real status transition to `withdrawn`, never a delete
  — consistent with the rest of the app never hard-deleting state. The Credits card shows only real
  applications; there is no fake "active loan" placeholder any more.
- **Transfer between my accounts** is a quick-access button on the Portfolio screen's accounts
  section. It calls the exact same `/payments/transfers` endpoint the "Between my accounts" tab of
  New Payment already uses — a second, more convenient front door onto the one existing money door,
  not a new pathway.

The Dashboard home screen's quick actions split the same way. **Add funds** is a mock top-up —
React state only, chosen deliberately over a real house-treasury deposit so it stays an obvious
sandbox action, not something that reads as a real funding rail. **Exchange** is real: see
"Exchange — real currency conversion" below. The home screen's account list is now a preview of the
first three accounts with a "see all" link to Portfolio, rather than the full list duplicated in
both places.

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
  goals/             savings goals — a real pot account plus a target, funded/topped up/withdrawn
                     via LedgerService.transfer; one active goal per user; standing orders
    goal.py          the Goal aggregate
    standing_order.py the StandingOrder aggregate
    service.py       create/close/deposit/withdraw, standing-order create/pause/resume/cancel/run
    validation.py    name, target amount/date, movement amount, frequency
  deposits/          term deposits — shaped exactly like goals/, minus the one-per-user limit
    deposit.py       the TermDeposit aggregate
    service.py       create/top-up/withdraw/close, rate looked up from products.catalogue by term
    validation.py    name, term-months whitelist, movement amount
  credits/           credit applications — a record only, no money movement, no approval
    application.py   the CreditApplication aggregate
    service.py       submit/withdraw, amount and term validated against products.catalogue
    validation.py    amount/term/purpose bounds
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
  vendors/           analytics over payments — no money movement. Only service.py is reachable
                     over HTTP; every other module is a manual batch job
    payments_adapter.py  the only file under vendors/ that names a `payments` field. Holds
                     the external-vendor filter, the field names, why each one is read the
                     way it is, and a startup guard that warns when that schema drifts.
                     `python -m backend.vendors.payments_adapter` prints the summary
    extractor.py     external-vendor filter, counterparty normaliser, monthly stats pipeline
                     into the rebuildable vendorMonthlyStats read model
    user_prices.py   per (vendor, user, month) price read model into vendorUserMonthlyPrices,
                     one median price per user-month so a personal baseline can be computed
    detector.py      two price signals into vendorAlerts — predictive, from users whose own
                     price rose against their own baseline or from a new shared price point,
                     and confirmed, from the vendor median. Baselines prefer the same month
                     last year so a seasonal tariff is not read as a price rise
    decision_engine.py  vendorAlerts -> userNotifications: one pending document per affected
                     user. Confidence follows the baseline alone — a year-old comparable is
                     trusted, a cold-start one is not — and never the alert type, so a seasonal
                     false positive cannot be promoted by arriving as a confirmed alert.
                     Romanian copy is templated off the vendor's category
    news_sources.py  the two article feeds — GNews (licensed, carries a summary) and Google
                     News RSS (headline only, no key, broad) — normalised to one shape and
                     merged on a folded title, since RSS links are Google redirects and never
                     match a publisher URL
    news_watcher.py  the external layer: a manual batch job that classifies those articles with
                     Azure OpenAI into newsSignals. Three cost gates stand before every paid
                     call — cross-source dedupe against already-seen, keyword filter over title
                     and summary, per-run call budget. Nothing is merged into the internal
                     signals yet
    news_events.py   groups newsSignals into newsEvents by event, so several articles about
                     one press announcement count as one confirmation and not as several
                     independent ones. Never writes to newsSignals — the source articles stay
                     traceable
    service.py       the only HTTP-facing module under vendors/. Reads userNotifications for
                     one signed-in user, deduplicates to the newest alert per vendor and caps
                     the list. A user with no notifications of their own gets an empty list —
                     it never substitutes another user's rows
  fx/                BNR reference-rate monitoring — read-only over accounts, no money movement.
                     Only service.py is reachable over HTTP; rates_watcher.py is a manual batch
                     job. Separate from vendors/ on purpose: a vendor price and a currency rate
                     are different signals with different orders of magnitude
    adapters.py      the only file under fx/ that names an `accounts` or `journalTransactions`
                     field. Holds the holding filter, the journal-derived balance pipeline, why
                     each field is read the way it is, and a startup guard that warns when
                     either schema drifts. `python -m backend.fx.adapters` prints the summary
    validation.py    rate scaling to micro-units, percent change, minor-unit conversion, the
                     ISO 4217 shape check the BNR feed is filtered through
    bnr_feed.py      the BNR XML feed — stdlib xml.etree, namespace-agnostic, divides out the
                     `multiplier` attribute so every stored rate is per one unit. Rejects a
                     non-XML answer instead of parsing it, which is what catches the old
                     www.bnr.ro/nbrfxrates.xml path now serving the redesigned homepage
    signals.py       the pure rule and copy: baseline resolution, the threshold test into
                     fxSignals, the repeat guard, and the RO/EN templates. No I/O, no Mongo
    rates_watcher.py the job: feed -> fxRatesDaily -> fxSignals -> fxNotifications, all three
                     idempotent on a unique key. Run by hand, never a daemon
    service.py       the only HTTP-facing module under fx/. Reads fxNotifications for one
                     signed-in user, newest per currency, capped — same scoping contract as
                     vendors/service.py
  capabilities/      SEAM 6: the registry an agent layer reads its tool list from
    registry.py      Capability, SideEffect, the in-memory CapabilityRegistry
    service.py       the registered capabilities — name, in/out schema, resolver, scope
    support_docs.py  parses frontend/help.html into searchable FAQ/guide entries
    analytics.py     the four analytics.* resolvers
    payments.py      balances, beneficiaries, and the money-moving transfer *proposal*
    cards.py         card list and the one card-action proposal
    investments.py   market snapshot over backend/investments/, preformatted
    products.py      deposit/credit catalogues and the two estimate calculators
  agents/            the workers — narrow callers of capabilities/, never of bus.execute
    adapters.py      AzureChatCompleter — Azure OpenAI, tool-calling
    base.py          ToolCallingAgent — the shared loop: capability-only, audits every run
    support.py       SupportAgent — read-only, FAQ/guide + own profile/sessions, tool-scoped
    analytics.py     AnalyticsAgent — read-only, forecasts and month-over-month explanations
    payments.py      PaymentsAgent — balances (read) + transfer proposals (money-moving)
    cards.py         CardsAgent — list, freeze/block, limits, issue, reveal; proposes only
    investments.py   InvestmentsAgent — real market prices, read-only, no advice
    deposits.py      DepositsAgent — product terms and maturity estimates, opens nothing
    credits.py       CreditsAgent — product terms and repayment estimates, decides nothing
    orchestrator.py  the lead agent: routes, fans out, aggregates; holds no capabilities
    transcript.py    sanitises the client-supplied conversation history
    service.py       wraps the actor as kind="agent", on_behalf_of=user_id
    analytics_service.py / payments_service.py   the same wrapping, per worker
    transcription.py AzureSpeechTranscriber — Azure AI Speech REST, one call, no tools
    transcription_service.py   the voice-input door: bounds, audit, never stores audio
  products/          static deposit and credit product terms (no persistence)
    catalogue.py     the rates and maxima the advisory agents quote
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
                     dashboard-screens.jsx (home, payments, chat, portfolio, cards, analytics,
                     education, settings)
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

## Investments — real prices, real trades

`backend/investments/` is the only feature that reaches outside the system for prices, and (like
`backend/exchange/`) one of the two feature folders approved to call `LedgerService.post_transaction`
directly for a trade — see rule 5 in `CLAUDE.md`.

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

The Portfolio screen no longer keeps its own holding list in `dashboard-data.js`: it builds the
row set straight from `market.quotes` (the full catalogue) and overlays each customer's real
`quantityMicro` from `GET /investments/portfolio` by `Instrument.id`, so a newly-listed instrument
in `CATALOGUE` appears with zero units automatically, with nothing to keep in sync by hand.

### Trading — gated by an investment account, real money

- `GET /investments/portfolio` — the caller's `invest`-kind accounts, each with its RON cash
  balance and its holdings, valued at the current live quote
- `POST /investments/buy` / `POST /investments/sell` — `{ accountId, instrumentId, amountMinorUnits }`,
  run through `bus.execute` like every other write: idempotent (`Idempotency-Key`), audited, one
  outbox event (`investments.bought` / `investments.sold`)

All three routes carry a `require_investment_account` dependency that 404s upfront if the caller
holds no active `invest`-kind account — the fast, UX-facing rejection. The actual security
boundary is inside the command handler itself, same as every other feature: it re-resolves the
account through `AccountsService.get_owned` (refuses one that isn't the caller's) and checks
`account.kind is AccountKind.INVEST` before doing anything else. A route-level check alone would
not be enough — nothing stops a handler from being called another way in the future — so the
guard lives in both places, exactly the pattern `exchange` and `payments` already use for
ownership checks.

A trade posts **one** `investment_buy` / `investment_sell` journal transaction, quantity computed
server-side from the *live* quote (never trusted from the client):

- **Buy**: `-amount` from the `invest` account, `+amount` into `house:invest_suspense:{currency}`.
- **Sell**: `-amount` from `house:invest_suspense:{currency}`, `+amount` into the account.

`house:invest_suspense` is a demo treasury exactly like `house:fx` and `house:settlement` — not a
real `Account` document, never balance-checked. Each trade also appends one row to the
append-only `investmentOrders` collection (`userId`, `accountId`, `instrumentId`, `side`,
`quantityMicro`, `unitPriceMinor`, `amountMinor`, `journalTransactionId`) — units are scaled by
1e6 (`quantityMicro`) the same way FX rates are scaled by 1e6, so fractional shares and crypto
never need a float. **Holdings are never stored as a mutable number**: a position is the signed
sum of that account's orders, computed on read —

```python
[
    {"$match": {"accountId": account_id}},
    {"$group": {
        "_id": "$instrumentId",
        "quantity": {"$sum": {
            "$cond": [{"$eq": ["$side", "buy"]}, "$quantityMicro", {"$multiply": ["$quantityMicro", -1]}]
        }},
    }},
]
```

against `investmentOrders` — the same "derive from an append-only log, never mutate a balance"
discipline rule 4 requires of the ledger itself. `MongoInvestmentOrderRepository.holdings_for_account`
(`backend/database/repositories.py`) runs exactly this pipeline; `InvestmentsService.portfolio`
joins its result with the live market snapshot to price each position.

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
  `backend/goals/` (below) — no goal set → `no_goal_found`. It also returns a
  `projectedCompletionDate` (today's date if the target is already met, `null` if the actual rate
  isn't positive, otherwise today plus the number of months the remaining gap needs at the actual
  rate) and a `streakWeeks` count — consecutive weeks, counting back from now, with a net-positive
  contribution to the goal's account, bucketed from a 26-week transaction lookback. Both are
  computed here, never by the model; `GET /goals/progress` (`server/routes.py`) exposes the same
  resolver output directly, read-only, for the Analytics screen's goal card below — one
  computation, two callers, the same numbers either way.
- `analytics.month_recap.get` and `analytics.what_changed.get` return facts only (biggest expense,
  busiest day, category deltas, per-category cause of a spend change — `new_merchant` /
  `increased_frequency` / `increased_price` / `no_clear_cause`), never prose; the agent's prompt
  does the narrating, so the numbers stay testable and localizable independent of phrasing.
- `analytics.recommendations.get` assembles up to three deterministic recommendations from the
  other resolvers' own logic — a `goal_projection` and a `savings_rate` entry (reusing
  `resolve_goal_gap`'s output directly) when a goal exists, and a `category_alert` entry when one
  category's spend grew ≥15% and ≥50 RON between the last two completed calendar months (the same
  significance thresholds `what_changed` uses). No goal and no notable category growth →
  `insufficient_data`. Every amount carries both the raw minor-units figure and a pre-formatted
  string (`currentValueFormatted`/`suggestedValueFormatted`/`gapFormatted`, same `format_minor` as
  `payments.balances.get`) — the prompt requires the model to quote the formatted string verbatim,
  after a first pass narrated raw minor units as if they were whole currency ("economisești acum
  33333 RON"), the exact failure mode `PaymentsAgent` had already hit once for balances.

All five page through the existing `PaymentsService.list_transactions` cursor (already sorted
newest-first) and stop once a page crosses the requested date boundary
(`capabilities/analytics.py::_transactions_in_range`) — no date-range parameter was added to
`payments/` or `ledger/` for this; that boundary stayed untouched on purpose. All five are also
scoped to RON transactions/accounts only: mixing currencies into one sum would be silently wrong,
and multi-currency forecasting was never asked for — an explicit v0 cut, not an oversight.
`GET /capabilities` describes all nine alongside the write-side command list.

**`backend/goals/`** exists only so `analytics.goal_gap.get` has real data to read — it followed
the same shape check as every other feature (aggregate, `service.py`, `validation.py`) and the same
one-write-path rule (`POST /goals` → `bus.execute(CreateGoal(...))`, `backend/goals/service.py`,
migration `ops/008_goals_schema.js`). v0 is **one *active* goal per user** — a `Goal` now carries a
`status` (`active` | `closed`), and the uniqueness is a **partial** Mongo index on `userId` where
`status: "active"` (`ops/011_goals_status.js`), not application code alone: closing a goal is a real
state transition (`POST /goals/{id}/close` → `bus.execute(CloseGoal(...))`), never a delete — the
document stays, just marked closed, matching how every other terminal state in this app works (a
blocked card, a rejected payment). Closing frees the slot for a new `CreateGoal` the same way it
always worked; there is still no *edit* endpoint, and still no support for more than one goal at a
time — replacing one means closing it and creating another, not editing it in place.

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
- **No usage cap of our own.** GEMS used to run a per-user sliding-window counter
  (`AgentRateLimiter`, 20 calls/hour, backed by an `agentRateLimits` collection). It is gone —
  the code, the settings, the collection and its tests. It was capping demos long before it was
  protecting anything, and the provider already enforces the limit that actually matters.
  **Azure OpenAI is now the only limiter.** Its 429 is caught in
  `AzureChatCompleter.complete` and re-raised as the same `RateLimitedError` (HTTP 429) the app
  already knew how to render, carrying `retryAfterSeconds` from Azure's `Retry-After` header when
  it sends one and a 20-second default when it does not — so the customer still sees a friendly
  "try again in a moment" instead of a 500, and the wait it quotes is the provider's real one.
  `backend/tests/test_azure_chat_completer.py` covers the header, the missing header and an
  unparseable header. What we lost with the counter: nothing now bounds a runaway agent loop
  per user, so a bug that asks in a tight loop is billable until Azure's quota stops it —
  `MAX_TOOL_ROUNDS` still bounds a single run, but not a caller.

`AnalyticsAgent` (`backend/agents/analytics.py`, `POST /agents/analytics/ask`) is the second
worker, built the same way: a thin `ToolCallingAgent` subclass supplying only a system prompt and
its `tool_names` allow-list (the four `analytics.*` capabilities above), same
`AnalyticsService` wrapper (`backend/agents/analytics_service.py`), same
audited-run-per-`run_id` guarantee, same in-code allow-list/`SideEffect.READ` enforcement — nothing
about the second worker changed how `ToolCallingAgent` works, which is the point of it being a
shared base. Its prompt carries one stake-appropriate addition beyond `SupportAgent`'s: every
number it says must come from a tool result, full stop, and any forecast or "capping X would help"
framing must be said as an estimate, not a certainty — financial projections, not FAQ answers.
`backend/tests/test_analytics_agent_scoping.py` mirrors `test_support_agent_scoping.py`'s allow-list
proof; `backend/tests/test_analytics_capabilities.py` exercises the five resolvers' actual logic
(recurring-pattern detection, the goal-gap rate math, the category-cause classifier, the
recommendations aggregation) against a scripted `PaymentsService`, no Mongo.

The Analytics screen (`SCR.AnalyticsScreen`, `frontend/components/dashboard-screens.jsx`) now
carries real frontend wiring for it, past the existing spend-by-category/income-vs-spend charts:
a **recommendations card**, which replaced the screen's old hardcoded "insight" blurb with a real
`askAnalytics(...)` call against `analytics.recommendations.get`, rendered with the same
`aiGenerated`/disclaimer treatment that blurb already used, and next to it a **goal card** reading
`GET /goals/progress` directly (a plain read, not narrated) for the progress bar, the projected
date, and a streak badge — shown only at 3+ weeks, and worded as a neutral nudge to start one below
that threshold, never as a broken-streak warning, per the stakes of encouraging compulsive
"catch-up" spending around money. When no goal exists, the goal card offers a **"Set a goal"**
button opening a dialog (name/description, target amount, target date, an account picker scoped to
the user's non-invest accounts) that posts to `POST /goals` — the first real caller of that
endpoint, closing the gap noted below. It is deliberately a normal confirmed UI action, not
something `AnalyticsAgent` can do on the user's behalf, matching the "agent proposes, human
confirms" line the rest of the app draws for anything that changes state.

**Financial education is its own screen**, not a card on Analytics: a new `education` nav entry
(`frontend/helpers/dashboard-data.js::navItems`, and the `SCREENS` allow-list in
`frontend/main/dashboard.jsx` — a screen key not in that array silently fails to navigate, which is
exactly how this one was missed on the first pass) renders `SCR.EducationScreen`: a grid of short,
hand-authored, non-personalized tips (`dashboard.education.*` in `messages.js`, no LLM call), plus
— at the requester's explicit request — the same live `RecommendationsCard` and `GoalProgressCard`
already on the Analytics screen, reused as-is rather than duplicated. The two are visually and
architecturally distinct on this page: the tip grid never calls out to a user's own data, the two
cards below it are exactly the personalized, agent-backed pair from Analytics.

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
enforcement, the `MAX_TOOL_ROUNDS` giving-up path, and the provider-429 mapping, all against a scripted
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

The same mis-typed-name slip resurfaced later, live, for `analytics.recommendations.get`:
gpt-5-mini called `recommendations.get` and, unlike the `transfer.propose` case, did not
self-correct within `MAX_TOOL_ROUNDS` — it repeated the exact same wrong name across all four
rounds despite the fed-back error naming the correct one, and the request failed with a 422. The
fix stops short of resolving a dropped prefix server-side (that would quietly change the
already-tested contract above, where an unrecognised name is always the model's problem to fix,
never the framework's to guess at) and instead makes the tool's `description` in the OpenAI
function-calling schema restate its own exact name (`backend/agents/base.py::_tool_defs`) rather
than just repeating the bare name as before — tool metadata the model weighs more heavily than
system-prompt prose for which literal string to echo back. Cheap, applies to every agent's every
tool, and left the retry contract and its tests untouched.

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
`CapabilityRegistry` at all — its only tools are the four workers plus `escalate_to_human`. It
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

There is no per-user call cap; Azure OpenAI's own quota is the only limiter (see above). The
orchestrator still holds the three agents directly rather than their services, so a fan-out is one
customer question rather than three trips through a service wrapper.

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

### Three advisory workers: investments, deposits, credits

`InvestmentsAgent`, `DepositsAgent` and `CreditsAgent` (`backend/agents/`) are read-only workers
the orchestrator can route to. All three are ordinary `ToolCallingAgent` subclasses with an empty
`proposal_tool_names`, so none of them can be handed a money-moving capability even by mistake —
`test_advisory_agents_explain_but_never_open.py` asserts exactly that against a registry that
deliberately contains `payments.transfer.propose` and `accounts.open`.

They differ sharply in how real they are, and the prompts say so out loud rather than hiding it:

- **Investments is real.** `investments.market.get` wraps the existing `backend/investments/`
  service, so prices, day change and the period low/high/change come from Yahoo and Frankfurter
  converted to RON. When the provider is down the capability passes `live: false` plus a
  `stalenessNote` instructing the agent to say so and give the timestamp before quoting anything.
  It cannot trade, and it gives no advice: no buy/sell/hold, no price predictions, no ranking
  instruments. It also cannot see the customer's *positions* — only prices — so "what are my
  holdings worth" is answered honestly rather than guessed.
- **Deposits and credits are catalogue-only.** `backend/deposits/` and `backend/credits/` are
  still empty folders; nothing about a term deposit, savings goal or credit application survives a
  refresh today. So these two agents explain products and do arithmetic, and nothing else.
  `backend/products/catalogue.py` is now the server-side source of truth for the terms and rates
  that `dashboard-data.js` renders in the mock UI — **the two copies are not yet linked, so a rate
  changed in one must be changed in the other.** The credits prompt is the strictest in the
  system: it may never say eligible, likely, pre-approved or refused, may never present a balance
  as an affordability assessment, and must say that no application is filed.

`deposits.maturity.estimate` and `credits.repayment.estimate` exist so the model never does money
arithmetic. Both take a rate the agent must have read from the catalogue — inventing or
interpolating one is forbidden — and both return preformatted strings plus a caveat (simple
interest, straight-line, no compounding, fees or tax) that the agent has to pass on. Every figure
crosses to the model already formatted, and the prompts forbid mentioning minor units or basis
points to the customer at all.

Verified live through the orchestrator: an ETF question routed to investments and quoted real
prices; "what rate on a 12-month term deposit" to deposits (6,10%, with the "I cannot open one"
caveat); "10.000 lei over 24 months" to credits, which **refused an invented APR** and used the
catalogue's 8,30%; and "open a 12-month deposit with 500 lei right now" produced an estimate and an
explicit refusal to open anything. Zero movement in `journalTransactions` or `payments` throughout.

Worth tuning: "should I buy Bitcoin?" and "am I approved for the mortgage?" both escalate to a
human rather than being declined by the specialist. That is defensible — a human does decide
credit — but it will generate handoff noise for questions the agents are already instructed to
decline politely. If that proves annoying, the fix is in the orchestrator prompt, not in the
workers.

### CardsAgent, and the auth hole it forced shut

`CardsAgent` (`backend/agents/cards.py`) covers the whole card surface: list, freeze, unfreeze,
block, ATM and online limits, issuing virtual or physical, and revealing the PIN or the details.
`cards.list` is a plain read; everything else goes through one `cards.action.propose` capability
registered `SideEffect.WRITE`. It **writes nothing** — it validates the action against the real
card's state and returns a proposal the customer confirms on screen, and the confirmation runs the
existing command through `bus.execute`. `ToolCallingAgent` was widened so `proposal_tool_names`
accepts `WRITE` as well as `MONEY_MOVING`; the invariant is unchanged and now broader: **no agent
ever writes, in any domain.**

Building it required closing the oldest hole in the repo. Every `/cards/*` endpoint took a
`username` in the body or query and ran as `Actor.public_cards()`, so anyone who knew a username
could list another customer's cards, change their limits, block a card, or reveal their PIN and
CVV — while `/accounts` had required a bearer token all along. An agent acting `on_behalf_of` a
signed-in user cannot work against that, because there is nothing to propagate. The commands now
carry no `username`, the routes take `CurrentActor`, and `CardsService` resolves the caller by
user id. `Actor.public_cards()` is gone. `GET /cards` without a token now returns 401.

**PIN and CVV never enter the conversation.** They would otherwise land in the model's context and
in the client-held transcript. `cards.list` returns only masked numbers, and a `reveal_pin` /
`reveal_details` proposal carries `revealsSecret: true` and no secret; confirming it navigates to
the Cards screen so the existing PIN gate runs there. `block` carries `irreversible: true` and
gets its own red-flag copy and confirm label. Tests assert no field of a card view or a proposal
can contain a PIN or CVV.

Verified live: routed correctly on all five card questions, refused to show a PIN in chat,
correctly refused to act on an already-blocked card, and asked which card when the customer had
two. With an unambiguous card named, all four proposal shapes came back correctly flagged — and
card states were byte-identical afterwards, with no card issued.

### The chat suggestions are real now

The three buttons above the chat box used to insert **canned answers** from `dashboard-data.js` —
the mock "Ionescu John" transfer card, a hardcoded table, a fake chart. They never called an
agent. They now send a real question through the orchestrator like anything the customer types.

They are also **contextual, for free**. The set shown is chosen from the agent that answered last
(`agentsUsed` on the orchestrator response), falling back to the current screen before a
conversation has started — so after a cards answer you get card follow-ups, after an analytics
answer you get spending ones. This deliberately costs no extra LLM call: generating follow-ups
with the model would add a round trip to every turn for suggestions people mostly ignore once
they start typing. Seven sets of three, `dashboard.chat.suggest.*`, en and ro.

Still canned: the **Ask GEMS dock's** per-screen prompt buttons, which remain wired to
`answerFor()` and `dashboard-data.js`. Only the chat screen's three were in scope here.

Not done: no mandates, no `settings.security.get` (see above), no
multi-goal support — the Analytics screen's "Set a goal" dialog only ever offers to create one, and
`backend/goals/` still enforces exactly one *active* goal per user. Replacing one no longer needs a
manual Mongo edit (see the "Financial education" section below for the close endpoint), but there is
still no edit-in-place: closing and re-creating is the only path.
`PaymentsAgent` cannot see transactions, cards or
settings, and `payments.transactions.list` is still not in the registry — add it there, not as a
new pathway, when a worker needs it. The proposal is stateless: `proposalId` is a display string,
nothing persists it, and the confirmation step re-validates from scratch rather than trusting it.

<<<<<<< HEAD
### Financial education — a RAG-backed advisor and in-chat goal setting

The Financial Education screen's earlier static tip grid was replaced by a real conversation panel
(`EducationChatPanel` in `frontend/components/dashboard-screens.jsx`), backed by a fourth
orchestrator worker, `EducationAgent` (`backend/agents/education.py`). This is the same class of
deliberate, explicitly-approved deviation past `PROMPT.md` §4 as the rest of the agent layer — a new
caller of the existing seams, not a new pathway.

`EducationAgent` reads from seven capabilities, all `SideEffect.READ`:
`education.docs.search` (a small hand-authored corpus — emergency funds, budgeting, compound
interest, inflation, term deposits, debt payoff order, diversification, the deposit guarantee
scheme, APR — in `backend/capabilities/education_docs.py`, scored by the same bag-of-words matcher
`support_docs.py` already uses, so it degrades to "here's the whole corpus" rather than inventing
an answer when nothing scores), plus `analytics.goal_gap.get`, `analytics.cashflow_forecast.get`,
`analytics.month_recap.get`, `analytics.what_changed.get`, `analytics.recommendations.get` and
`payments.balances.get` reused as-is for personalised advice grounded in the customer's own
numbers. The three transaction-reading analytics tools are the difference between advice about the
customer's *money* and advice about their one savings goal: without them the agent could only ever
personalise around a goal, and had nothing to say to a customer who has not set one.

`analytics.recommendations.get` is the same widening on the capability side. It used to lead with
two goal-derived entries (`goal_projection`, `savings_rate`) and add at most one `category_alert`;
it now also returns a `spending_cap` on the largest discretionary category
(`_DISCRETIONARY_CATEGORIES`, trimmed by `_SPENDING_CAP_TRIM_PCT` — both constants had been sitting
unused), every category that grew past the significance thresholds rather than only the worst one
(`_MAX_CATEGORY_ALERTS`), a `recurring_spend` roll-up of the subscriptions `_detect_recurring_groups`
already finds for the cashflow forecast, and — when there is no goal — a `savings_rate` computed
from last month's income against last month's spend. Every entry still carries its own pre-formatted
strings; the agents are still forbidden from doing arithmetic. This is what the "Personalized
recommendations" card on the Education screen renders, so that card no longer degrades to goal talk
for a customer without a goal.

**Setting a goal from the conversation** is the one new write-shaped capability,
`goals.create.propose` (`backend/capabilities/education.py::resolve_goal_proposal`), built the same
way `payments.transfer.propose` was: it validates and computes a fully-formed goal (account, name,
target amount, target date) and **returns a proposal, never persists one** — no call to
`GoalsService.add`, mirrored by `backend/tests/test_education_capabilities.py`'s "never creates the
goal" proof, the same shape as `test_payments_agent_proposes_but_never_pays.py`. The customer
confirms it as a card in the chat panel, which calls the existing `POST /goals` — the same command
`SetGoalDialog` already uses — so a goal is still only ever created through one path.

`GoalProposalInput` also takes an optional `currency`, the ISO code of the currency the customer
named the amount in. A customer holding both "Cont curent" (RON) and "Cont curent USD" made
`accountRef: "curent"` tie on `_match_score`, so the proposal came back `needs_clarification` and no
card ever appeared — the customer asked for a goal and got a question instead. The currency only
breaks a tie: it narrows an already-ambiguous match set, and if none of the tied accounts hold it
the proposal still asks. `_match_score` and `_resolve_ref` in `backend/capabilities/payments.py` are
untouched, so the money-moving transfer proposal keeps its stricter behaviour.

The one piece of shared infrastructure this needed: `ToolCallingAgent`'s proposal path
(`backend/agents/base.py`) only recognised `SideEffect.MONEY_MOVING` as proposable. `goals.create`
is not money movement, so `SideEffect.WRITE` (already in the enum, unused until now) is now
accepted there too, additive and backward compatible — every existing `MONEY_MOVING` test is
unaffected (`backend/tests/test_education_agent_scoping.py` proves the widening only reaches a
capability actually granted to an agent's `proposal_tool_names`, same as before). This preserves the
"agent proposes, human confirms" rule the analytics goal card already drew a hard line at, rather
than letting an agent write to Mongo directly.

**Closing a goal** (`POST /goals/{id}/close` → `bus.execute(CloseGoal(...))`,
`backend/goals/service.py`) is the piece this unblocked: since only one *active* goal is allowed per
user, the chat panel's "set a new goal" path needed a real way out of an existing one, instead of a
manual Mongo edit. `Goal` gained a `status` (`active`/`closed`); the row is never deleted, only
transitioned, and the uniqueness moved from a plain unique index to a **partial** one on `userId`
where `status: "active"` (`ops/011_goals_status.js`) — so the DB itself still enforces "one active
goal," not just application code, exactly as before. `GoalProgressCard`
(`frontend/components/dashboard-screens.jsx`) exposes this as a "Close this goal" link behind a
confirm dialog; once closed, `GET /goals/progress` naturally reports "no goal" again (it already
reads through the same `status`-filtered `get_for_user`), so the existing "Set a goal" flow just
works without any new frontend state.
=======
## Voice input — dictation, not a second way in

The microphone next to Send in the AI Assistant chat records with the browser's own
`MediaRecorder`, posts the clip to `POST /agents/transcribe`, and drops the returned text **into
the input box**. Nothing is sent, asked or moved by speaking: the customer still reads what was
heard, edits it, and presses Send, which then takes the ordinary `POST /agents/ask` path. Voice is
a keyboard, not a new pathway — the seven seams are crossed by the message the user finally sends,
exactly as if they had typed it.

`AzureSpeechTranscriber` (`backend/agents/transcription.py`) talks to **Azure AI Speech**, not
Azure OpenAI — a different service with a different key, so it shares nothing with the
`AZURE_OPENAI_*` pair. It is one POST to the fast-transcription REST endpoint
(`/speechtotext/transcriptions:transcribe`), no SDK, no tools, no capability registry, built lazily
like the workers, so a clone without `AZURE_SPEECH_API_KEY` still boots. The URL comes from
`AZURE_SPEECH_REGION` alone; `AZURE_SPEECH_ENDPOINT` overrides it for a custom resource host, and a
404 is turned into an error that names that as the likely cause — Speech Studio shows an
`*.stt.speech.microsoft.com` endpoint that belongs to a *different* API and will not answer here.

Both locales are always sent as candidates (`ro-RO`, `en-US`), with the interface's own language
first, so Azure runs language identification rather than being told what it will hear. A customer
whose interface is in English can still dictate in Romanian, which in this market is the normal
case, not the edge one.

`TranscriptionService` is the door: an empty clip, a clip over `SPEECH_MAX_UPLOAD_BYTES`, or a
format Azure does not accept is refused **before** the network call, and only then does the audio
leave. The browser stops recording on its own after 60 seconds, so the byte cap is a second line
rather than the first. There is no usage counter of our own, for the same reason the chat path no
longer has one (see "No usage cap of our own" above): **Azure is the only limiter**, and its 429 is
caught in `error_for_status` and re-raised as the same `RateLimitedError` the app already renders,
carrying `retryAfterSeconds` from `Retry-After` when Azure sends one and the shared 20-second
default when it does not.

The audio is never stored and never reaches the journal. The audit row
(`agents.voice.transcribed`, `entityType: "voice_input"`) records the actor, byte count, content
type, language hint and the *number of characters* heard — never the words themselves. If the
customer acts on what was dictated, the sentence is audited then, on the message they chose to
send. `backend/tests/test_voice_input_is_bounded_and_never_transcribed_into_the_audit_log.py`
defends both halves against a fake transcriber, and
`backend/tests/test_azure_speech_transcriber.py` covers the adapter's own shaping — locale
candidates, phrase joining, endpoint-vs-region, and which HTTP status is the caller's fault versus
ours. No network in either.

Not done: no streaming (the clip is transcribed once, on stop, not as you speak), no
speaker verification, no server-side language detection beyond the `ro`/`en` hint the interface
already knows, and no voice on the docked assistant — only the full chat screen.

## Voice output — text-to-speech for the AI Assistant

`AzureSpeechSynthesizer` (`backend/agents/synthesis.py`) powers speech synthesis for the AI Assistant
via Azure AI Speech (`POST /agents/synthesize`). It maps `ro` to `ro-RO-AlinaNeural` and `en` to
`en-US-JennyNeural`, building SSML with XML escaping and returning standard MP3 audio streams.

`SynthesisService` (`backend/agents/synthesis_service.py`) validates text non-emptiness and caps
length at `SPEECH_TTS_MAX_CHARS` (5,000 characters). Auditing (`agents.voice.synthesized`,
`entityType: "voice_output"`) logs character count, language, and byte count without persisting the
spoken words in the journal.

In the frontend, every AI message bubble includes a "Read aloud" speaker button for on-demand playback,
and toggling Read Aloud in Settings or the chat header automatically reads incoming assistant responses
aloud with seamless in-memory audio caching and client-side `window.speechSynthesis` fallback.
>>>>>>> f246952780604fd79494ff16c6ba4db93b0d52b8

## Savings goals: many at once, with a real streak

> The conflict block immediately above this section is an **unresolved merge conflict committed to
> `main`** in `af2f062` ("fixed app"). Both of its sides describe the superseded "one active goal
> per user" model. It needs the goals track's owner to resolve it; this section documents what the
> code actually does now.

**One active goal per user is gone.** A user may hold any number of active goals in parallel, each
with its own savings pot, target, projection and streak.

The single-goal rule was never enforced in one place, which is what made it fail. It lived in three:
a `ConflictError` in `GoalsService._handle_create`, a `get_for_user` query, and a unique Mongo index.
`ops/011_goals_status.js` was supposed to replace the plain unique index `uq_user`
(`ops/008_goals_schema.js`) with a partial one, but **on any database where 011 was never applied by
hand, `uq_user` survived** — and a plain unique index on `userId` rejects a second goal whether the
first is active or closed. Closing worked correctly; creating the replacement then failed on a
`DuplicateKeyError` that `MongoGoalRepository.add` relabelled as "You already have a goal", naming a
constraint that was not the one firing. That is the whole bug.

Both indexes are now gone, replaced by a non-unique `ix_user_status` on `{userId, status}`.
Because the original failure was a migration that never ran, `ensure_indexes`
(`backend/database/mongo.py`) **drops every unique index on `goals` except `_id_`** before creating
the new index, so neither an unapplied migration nor a legacy index under some other name can
resurrect the bug. `ops/013_goals_multi_and_streak.js` records the same change for databases rebuilt
from the migration set.

The shared demo database is written by several API instances at once, and one still running
pre-fix code re-creates `uq_user_active` at its own startup. Dropping the index once therefore does
not hold. `_index_reassert_loop` in `backend/main.py` re-runs `ensure_indexes` every
`INDEX_REASSERT_SECONDS` (default 300) so that drift is corrected without waiting for a restart;
`create_index` is a no-op when the index already matches, so the loop only ever removes the legacy
unique index. It is a guard for a shared demo database, not a substitute for every instance running
current code.

**Closing a goal is still a status transition, never a delete** — the history is needed for streaks
and reporting. Closing now also refuses to touch the funding account when a goal's `accountId`
equals its `parentAccountId` (`Goal.uses_shared_parent_account`); see the risk note below.

**The streak is derived and persisted.** `backend/goals/streak.py` counts consecutive ISO calendar
weeks with at least one credit into the goal's pot, reading the pot's own journal movements — the
ledger stays the source of truth, and the count is a rebuildable read model stored on the goal as
`streakWeeks` / `streakLastWeek` / `streakComputedAt`. It is refreshed inside the command-bus
handlers that can change it (deposit, withdraw, standing-order run), so the write still goes through
the one write path. Read paths derive it fresh, so a streak that lapses is shown as lapsed
immediately rather than waiting for the next contribution.

`analytics.goal_gap.get` and `analytics.goal_pace.get` no longer compute a second, different streak
from the payments list; they report the goals service's number, so the agent's narration and the
card on screen can never disagree. Both capabilities now honour the `goalId` they already accepted,
so each goal can be projected independently.

`GET /goals` returns every active goal with its progress, streak and projection.
`GET /goals/progress` and `GET /goals/pace` still answer for a single goal, unchanged, so the
existing agent tools keep working.

**Financial education content.** `backend/capabilities/education_lessons.py` holds eight
micro-lessons, **each carrying its own five-question quiz** (40 questions in total), as frozen
dataclasses in EN and RO, following `education_docs.py` — static seed content, no CMS, no
collection, no generation flow. `GET /education/lessons` serves each lesson with its questions
nested inside it. Each lesson card has a "Start quiz" button that opens the quiz as a modal
(`QuizDialog`); on submit it shows the score, marks the correct answer on every question, and
explains each one. Grading happens in the browser and nothing about an attempt is persisted, so the
quiz adds no write path and no new collection.

**Reading the goal.** The projection is a **progress ring**, not a line chart: percentage, amount
saved and target in the centre, with a slider beside it for "if I put aside this much each month".
Moving it recomputes the completion date live, entirely client-side from figures the API already
returned, and the result is tinted by whether that pace still meets the target date. A one-tap hint
sets the slider to the rate the goal actually needs. The earlier two-series line chart was replaced
because it was hard to read at a glance and never answered the question the user was actually
asking.

### Known risk: legacy goals whose pot is the account that funds them

`ops/012_savings.js` backfilled `parentAccountId = "$accountId"` for goals created before dedicated
pots existed. For those rows the pot **is** the funding account, and the close path used to sweep
the pot into the parent and then close it. On the shared demo database that has already happened
once: a goal closed on 2026-08-28 posted journal transaction `01a04742-8a4a…` with both entries on
account `01a01ed4-9a3a…` (`-79140` and `+79140` — balanced, so the double-entry constraint passed,
but economically a no-op now permanent in an append-only journal), and then closed that account,
which was the customer's main current account. `JournalTransaction.entry_for` returns only the first
matching entry, so that transaction also renders misleadingly in a statement.

The close path is now guarded, so this cannot happen again. **The existing damaged data has been
left exactly as it is** — the closed account and the self-transfer are the goals track's to decide
on, and the journal is append-only in any case. Affected rows are visible with
`db.goals.find({$expr: {$eq: ["$accountId", "$parentAccountId"]}})`.


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

## Agent insights on the dashboard

The AGENT INSIGHTS card reads `GET /api/insights`. The user id comes from the session actor, not
from a query parameter, so the endpoint is scoped to the signed-in user and nothing else: a user
with no notifications of their own gets an empty card.
It never falls back to another user's rows — an earlier version did, and showed one synthetic
user's bill as if it were yours.

`userNotifications.userId` must therefore hold a real `users._id`. The synthetic cohort in
`payments_seed_dev` / `payments_seed_seasonal` uses generated ids that match no real account, so
those rows are unreachable by design. To give a real account its own history, seed it into its
own source collection:

```bash
python -m ops.seed_vendor_payments --collection payments_seed_demo --batch vendor-demo-v1 \
  --months 18 --increase-month-index 14 --seasonal --real-user gabriela --vendor-increase enel
python -m backend.vendors.extractor       --source payments_seed_demo
python -m backend.vendors.user_prices     --source payments_seed_demo
python -m backend.vendors.detector        --source payments_seed_demo
python -m backend.vendors.decision_engine --source payments_seed_demo
```

`--real-user` resolves the username against `users`, debits their real RON account, and fails
loudly if either is missing — seeding a history for an account that does not exist is the bug
this flag exists to prevent. The synthetic cohort is still generated alongside them, because
`detector.py` needs at least `min_cohort_users` (2) per vendor before it will raise anything.

`--vendor-increase KEY` applies that vendor's `tariff_increase` from the increase month onward.
It is opt-in so a re-run without it reproduces the older collections byte for byte. Enel carries
a 22% rise, and 18 months of history is what makes it visible for the right reason: the detector
then has the same month last year to compare against, so the winter seasonal swing cancels out
and only the tariff rise is left. With a short history the same data yields a `rolling_3_month`
baseline, the alert comes out `low`, and it is suppressed.

`vendor_insights_source` and `vendor_insights_limit` in `backend/config.py` select which source
collection the card reads and how many vendors it shows. The card itself renders the first
`INSIGHT_CARD_LIMIT` of those and offers "view all" when there is more — the backend decides
which alerts and in what order, the frontend only decides how many fit. The full list collapses
a predictive and a confirmed alert for the same vendor and month into one row: that is one price
rise seen by two mechanisms, not two rises.

One price rise is one notification. `vendorAlerts` and `newsEvents` keep every month and every
article — the filter sits only where rows reach the user:

- **A persistent rise is not re-sent every month.** A year-over-year baseline moves from month to
  month even when the tariff behind it never changed again, so comparing baselines cannot tell a
  reconfirmation from a new rise. `decision_engine.py` instead remembers the price state it last
  notified per (user, vendor, currency) and suppresses a new row while *either* the absolute price
  *or* the size of the step is materially unchanged — `repeat_price_tolerance` (3%) and
  `repeat_step_tolerance` (12pp). A flat vendor is caught by the price test, a seasonal one whose
  bill keeps sliding by the step test. Only when both have moved is it treated as a new rise.
- **Later articles about a known announcement enrich it, they do not repeat it.** News events are
  grouped once more into episodes — same vendor, compatible market and percent, within
  `news_episode_window_days` (180). Dated and undated events are grouped separately, so a dated
  foreign announcement never absorbs undated domestic coverage. Once an episode has notified a
  user, further events in it add their publishers to that row's source list instead of creating
  another.

Both suppressions are recorded in the run report as `same_price_state_already_notified` and
`same_news_episode_already_notified`, so nothing disappears silently.

Money is never formatted in the backend. `decision_engine.py` writes `longText` / `longTextEn`
with `{baseline}` and `{observed}` placeholders plus the minor-unit values, and the frontend
fills them through `UI.formatMoney`, so the card follows the same locale rules as the
transactions table — `1.234,00 RON` in Romanian, not `1,234.00`.

## FX insights — the BNR reference rate on the dashboard

A second, separate pipeline. A vendor raising a subscription and the leu moving against the euro
are different signals: different source, different cadence, different order of magnitude. They
share nothing but the card they land on, so `backend/fx/` shares no collection, no schema and no
threshold with `backend/vendors/`.

**Source.** The public BNR XML feed, free, no API key:

| feed | url | contents |
| --- | --- | --- |
| daily | `https://curs.bnr.ro/nbrfxrates.xml` | the latest banking day, 37 currencies |
| last 10 days | `https://curs.bnr.ro/nbrfxrates10days.xml` | the last 10 banking days |

Both live on `curs.bnr.ro`, **not** on `www.bnr.ro`. The historical `www.bnr.ro/nbrfxrates.xml`
path now 302s to the redesigned homepage and answers `text/html`, so `bnr_feed.fetch_feed`
refuses any answer whose content type is not XML rather than handing an HTML page to the parser.
BNR publishes after 13:00 on banking days, so the newest cube in the feed is often *yesterday*.
Every row is dated by the feed's own `Cube date`, never by the machine clock.

Rates are stored as integer micro-units (rate × 10⁶), the same scale `backend/exchange/` already
uses — a rate is not money, so the minor-unit rule does not apply, but no float reaches Mongo
either. The feed's `multiplier="100"` attribute is divided out on the way in, so every stored
rate is RON per **one** unit regardless of how BNR quotes it.

**Which currencies.** Not all 37. The tracked set is the non-RON currencies actually held in
`accounts`, unioned with `SUPPORTED_CURRENCIES - {RON}` so EUR and USD are always covered even
before anyone opens such an account. `--currency EUR` overrides it.

**The rule.** Per currency, the latest published rate against the last rate published on or
before `baseline_days` (7) earlier — nearest-on-or-before, so a weekend or a holiday falls back
to the previous banking day instead of losing the comparison. Over threshold in either direction
becomes one row in `fxSignals` with `direction: "up" | "down"`.

The threshold is `0.5%`, not the 8%/12% the vendor pipeline uses. Currency rates move roughly an
order of magnitude less than consumer prices — EUR/RON moved 0.26% over the week of 2026-08-26 and
USD/RON 0.55% over the week of 2026-08-28 — so reusing a vendor-sized threshold would mean the
rule never fires and a rate crisis would look identical to a quiet week. It started at `1.5%`,
which on a leu this tightly managed against the euro is the same mistake one order of magnitude
smaller: no week in the feed's ten-day window ever reached it.

**Who hears about it.** Only a user with a positive balance in that currency. There is no
read-only accounts adapter equivalent to `vendors/payments_adapter.py` — `accounts/service.py` is
DI-wired into the app and unreachable from a standalone job — so `backend/fx/adapters.py` is that
adapter, and every assumption it makes is printed by `python -m backend.fx.adapters`. The balance
is **derived from journal lines**, mirroring `MongoJournalRepository.balances_for`; there is no
balance field to read (rule 4). Several accounts in the same currency fold into one holding.

**Idempotence.** All three collections upsert on a unique key: `fxRatesDaily` on
`(source, currency, date)`, `fxSignals` on the same, `fxNotifications` on
`(source, userId, currency, signalDate)`. Re-running the job any number of times replays the same
documents. Beyond that, a *continuing* move is not re-announced: a signal on a later date whose
current rate is within `repeat_rate_tolerance_percent` (0.5%) of what that user was last told is
skipped as `same_rate_state_already_notified`, exactly as the vendor pipeline suppresses a
persistent price. Only a genuinely new move notifies again.

**Copy.** Templated off the signal, never per currency — one Romanian and one English template
carrying the currency, the direction verb, the percent and the window, and nothing else. One
sentence, under 90 characters:

> EUR a crescut cu 0,3% în 7 zile — soldul tău de **{amount}** valorează acum **{ron}**, față de **{ronBefore}**.
> EUR rose 0.3% in 7 days — your **{amount}** is now worth **{ron}**, vs **{ronBefore}** before.

`{ronBefore}` is the *same* balance valued at the baseline rate, not what the account held a week
ago — it isolates the rate move from any deposit or conversion the user made in between, which is
the only comparison the rate alone can honestly support.

The two raw rates stay in `baselineRate` / `currentRate` for anyone reading the API or the
collection; they are not read out in the sentence. Money stays unformatted in the backend:
`longText` carries `{amount}`, `{ron}` and `{ronBefore}` plus `amountMinorUnits` /
`ronEquivalentMinorUnits` / `ronBaselineMinorUnits` / `currency` / `ronCurrency`, and the frontend
fills them through `UI.formatMoney`, same as the vendor card. `{ronBefore}` is substituted before
`{ron}` so the shorter key cannot eat the longer one.

**Provenance.** Every notification carries `sourceName` and `sourceUrl`, and the card renders
them as a clickable line under the text. For FX that is BNR's own page describing the feed
(`bnr_fx_source_page_url`, overridable with `--source-page-url` — the old `.aspx` paths now
redirect to the homepage, so this one is configuration, not a constant). Vendor insights link to
the first URL in `newsUrls`, labelled with the publishers; an insight with no external source
(`origin: internal_mathematical`) says so in words instead of offering a dead link.

**The endpoint.** `GET /api/insights` was extended rather than duplicated, and the
FX rows sit in their own `fx` key:

```json
{ "insights": [...], "history": [...], "total": 3,
  "fx": { "insights": [...], "history": [...], "total": 2 } }
```

One request, one `useEffect`, and the vendor contract is byte-identical to what it was — nothing
nullable was added to `VendorInsight` to make a currency fit a vendor shape.

The card shows exactly two stories: the newest vendor one and the newest exchange-rate one
(`INSIGHT_CARD_LIMIT`, applied per kind). Everything else — the rest of both histories — is
behind "view all", where the dialog lists them under separate headings. The backend still decides
which rows and in what order; the frontend only decides how many fit.

**Running it.**

```bash
python -m backend.fx.rates_watcher                        # today's rates, then signals
python -m backend.fx.rates_watcher --backfill-history     # also pull the 10-day feed first
python -m backend.fx.rates_watcher --dry-run              # fetch and report, write nothing
python -m backend.fx.rates_watcher --threshold-percent 0.5 --baseline-days 14
python -m backend.fx.adapters                             # what fx/ assumes about accounts
```

A first run on an empty `fxRatesDaily` has no baseline and reports `no_baseline_in_window` for
every currency — correct, not a failure. `--backfill-history` seeds ten banking days from the
second feed in one go so the rule has something to compare against immediately.

Checking it in mongosh:

```js
db.fxRatesDaily.find({currency:"EUR"}).sort({date:1})
db.fxSignals.find().sort({date:-1})
db.fxNotifications.find({userId:"<users._id>"})
db.fxRatesDaily.getIndexes()          // fx_rate_unique on (source, currency, date)
```

`--source` labels every row the run writes, so a demo run at a lower threshold can be told apart
from a production one and deleted on its own.

## What backend/vendors/ assumes about `payments`

`payments` belongs to the Payments & Cards track. `backend/vendors/` only ever reads it,
never writes, and every assumption is centralised in `backend/vendors/payments_adapter.py`
so a schema change breaks one file loudly instead of six quietly.

A payment counts as "to an external vendor" when all of these hold:

| condition | why |
|---|---|
| `status` is `posted` | only settled money belongs in a price statistic; a rejected payment would poison a vendor's max and median |
| `targetAccountId` is `null` | the structural discriminator. `payments/service.py` asserts it is set before posting and money can only reach a GEMS account, so a posted payment with it set *is* an internal P2P transfer — guaranteed by code, not by user input |
| `rail` is not `internal` | secondary check. System-assigned and enum-constrained, never typed by a customer. Excluded rather than whitelisted, so a new external rail is picked up automatically |
| `amountMinorUnits` > 0 | integer minor units; the money core forbids floats |
| `counterparty` is a non-empty string | it is the vendor identity, after folding |

Fields read, and what each is used for:

| field | used for |
|---|---|
| `userId` | per-user price history and cohort counts |
| `targetAccountId` | the external-vendor discriminator above |
| `rail` | secondary discriminator; also reported per vendor |
| `status` | settlement filter |
| `amountMinorUnits` | the price — min, max, median, per-user series |
| `counterparty` | vendor identity, folded for diacritics, case and whitespace |
| `category` | reported only |
| `currency` | part of every grouping key, so RON and EUR never mix |
| `createdAt` | the month a payment is bucketed into, in Europe/Bucharest |

**`category` is deliberately not a discriminator.** It is chosen by the customer from a
whitelist, and on real data 6 of 13 P2P transfers carry `utilities`, `entertainment`,
`transport` or `groceries` rather than `transfer`. Filtering P2P on
`category == "transfer"` misses about 46% of it.

If any of this changes, `backend/vendors/` prints a loud warning at startup and keeps
going — it never silently returns nothing. The fix is always in `payments_adapter.py`.

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
