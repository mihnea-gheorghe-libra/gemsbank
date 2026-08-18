# Design notes — `design/export/` → the app

**Phase 0 deliverable.** Status: **awaiting confirmation** (PROMPT.md §3.5 gate).
Source archive: `design/export/GEMS Banking.dc.html` + `industry.css` (base design system)
+ `gems-theme.css` (GEMS theme layer). Extracted 2026-08-18.

**Fidelity rule (PROMPT.md §3):** the archive dictates *look*. `PROMPT.md` and
`docs/ARCHITECTURE.md` dictate *structure, routes and data*. Where they disagree, structure wins
and the disagreement is logged in §4 below.

---

## 1. What the archive actually is

Not a set of static HTML screens. It is a **single Claude Design canvas component** — one
`1440×900` artboard with a JS state machine (`state.screen`) that swaps between **nine screens**,
plus a prop-driven Light/Dark toggle and a floating agent dock. Consequences:

- There is **one** HTML file, not nine. Screens are `<sc-if>` branches, not documents.
- All styling is inline `style="…"` attributes referencing `var(--color-*)`. The tokens are real
  and extractable; the layout markup is not directly reusable.
- The canvas is **fixed-size desktop**. It contains **zero `@media` queries** (§4.1).
- Demo data is hardcoded Romanian retail banking (RON amounts, `Kaufland Băneasa`, `Enel Energie`,
  `Salary — Nexo SRL`), which confirms `ro` as the default locale.

## 2. Screen → route map

The archive's own numbering (`SCREEN 01`–`09`) is kept in the first column for traceability.

| # | Screen in archive | Route | v0? |
|---|---|---|---|
| 01 | Onboarding & KYC (5-step wizard) | `/register` — **reduced** to email + password, no KYC steps | partial |
| 02 | Authentication (PIN pad, captcha after 3 fails) | `/login` — **password**, not PIN (§4.4) | partial |
| 03 | Dashboard | `/dashboard` | built |
| 04 | Accounts & portfolio | `/dashboard` (list) + `/accounts/[id]` (detail) | built |
| 05 | Payments & transfers | `/transfer` | built, internal only |
| 06 | Card management | `/cards` — **stub page, "coming soon"** | out |
| 07 | Analytics & statistics | `/insights` — **stub page, "coming soon"** | out |
| 08 | AI agent chat | *no route in v0* — the agent dock is **not rendered** | out |
| 09 | Settings | `/settings` — **one real preference**: hide balances | built, reduced |

Archive screens 06, 07 and 08 are **out of v0 scope** (`PROMPT.md` §4). Per the no-dead-links
rule they get a route that renders a visible "coming soon" state — never a 404, never a nav item
that goes nowhere.

The archive's left nav lists seven items (`Dashboard, Payments, AI Assistant, Portfolio, Cards,
Analytics, Settings`). v0 renders all seven, with `AI Assistant`, `Cards` and `Analytics`
visibly marked as unavailable rather than removed — removing them would make the shipped nav
disagree with the design, and marking them keeps the growth path visible.

## 3. Repeated visual block → component map

| Block in archive | Component | Notes |
|---|---|---|
| Left rail with numbered pill tabs (`.gemsnav`) | `components/layout/SideNav.tsx` | active = plum fill + lime numeral |
| Top bar: greeting, screen tag, theme + balance toggles | `components/layout/TopBar.tsx` | Client Component (toggles) |
| `.blueprint` framed plate | `components/ui/Plate.tsx` | GEMS drops the corner registration marks |
| Balance / account summary tile | `components/money/AccountTile.tsx` | consumes `<Money>` |
| Any currency amount | `components/money/Money.tsx` | **the only formatter** — minor units + ISO code via `Intl.NumberFormat` |
| Transaction row (date, payee, ref, category, status, amount) | `components/money/TransactionRow.tsx` | sign glyph + text label, never colour alone |
| Transaction list + filters (`All`, segmented control) | `components/money/TransactionList.tsx` | cursor pagination |
| Status pill (`Booked` / `Pending`) | `components/ui/Tag.tsx` | maps the payment state machine |
| Segmented control (`.seg`) | `components/ui/Segmented.tsx` | radio group under the hood, keyboard-navigable |
| Pill button (`.btn`) | `components/ui/Button.tsx` | primary / secondary variants |
| Labelled input (`.field` + `.input`) | `components/ui/Field.tsx` | label always present, never placeholder-as-label |
| New-payment form (beneficiary, IBAN, amount, currency, reference) | `app/(app)/transfer/` | server action to `POST /payments/transfers` |
| "Continue to signature" confirm step | `components/money/ConfirmTransfer.tsx` | renders **real** state incl. `pending` |
| Settings section (kicker + rows) | `components/layout/SettingsSection.tsx` | only the hide-balances row is live in v0 |
| *(no precedent in archive)* incident banner | `components/status/StatusBanner.tsx` | §4.5 |

## 4. Conflicts between the archive and PROMPT.md / ARCHITECTURE.md

These are the resolutions. Each one is a place where I did **not** follow the design.

### 4.1 No responsive design at all

The archive has zero `@media` queries and a fixed `1440×900` canvas with `overflow:hidden` and
`height:100vh`. `PROMPT.md` §0 targets "desktop and mobile" (`c1-context.mmd`).
**Resolution:** build mobile-first from the desktop composition; breakpoints in `tokens.css` are
**ours**, flagged as such in `tokens.extracted.json`. The fixed-viewport `overflow:hidden` shell
is dropped — it breaks zoom and reflow (WCAG 2.2 AA 1.4.10).

### 4.2 No debit/credit colours, and a lime ramp that fails contrast

The archive signals money direction with the glyph `−` / `+` only, and defines no
positive/negative/warning roles. Separately, lime steps 600–800 measure **3.9–4.1:1** on both
light grounds — below AA for normal text.
**Resolution:** derived `positive` / `negative` / `warning` tokens, contrast-verified, with their
measured ratios recorded in `tokens.extracted.json`. The sign glyph stays as the primary signal,
so WCAG 1.4.1 holds (colour is never the only channel) — colour is reinforcement. Lime 600–800
restricted to decorative and large-text use; lime 900 for text.

### 4.3 Non-integer spacing scale

`industry.css` uses a `3.4px` base (`3.4 / 6.8 / 10.2 / 13.6 / 20.4 / 27.2`), which produces
sub-pixel rounding at every step.
**Resolution:** rounded to a 4px grid (`4 / 8 / 10 / 14 / 20 / 28`). Maximum drift 0.8px.
Visually indistinguishable; removes a class of rendering inconsistency.

### 4.4 Authentication is a 4-digit PIN; PROMPT.md §4 requires a password

The archive's sign-in is a 4-cell PIN pad with a captcha after 3 failures. A 4-digit PIN is a
10⁴ keyspace — acceptable only as a *device-bound* second factor behind a real enrolment, which
v0 does not have.
**Resolution:** `/login` is **email + password (Argon2id)** per `PROMPT.md` §1. The PIN pad
composition is kept as the visual treatment for the **step-up challenge**, which is where it
actually belongs — `identity`'s step-up port, stubbed in v0. Logged here rather than silently
redesigned.

### 4.5 The archive has no incident/status banner

`PROMPT.md` §4 requires `GET /system/status` and a dismissible in-app banner — the single
most-cited market gap (`ARCHITECTURE.md` §2).
**Resolution:** `StatusBanner` is built from the design's `.blueprint` plate plus the `warning`
token. It is the one component with no precedent in the archive.

### 4.6 The cards screen renders card numbers

Archive screen 06 shows masked PANs (`•••• •••• •••• 4127`), expiry dates and a "show PIN"
control. `PROMPT.md` §0 forbids code that pretends to process real card data.
**Resolution:** `cards` stays a README-only module and `/cards` is a stub. No card data model, no
masked-PAN component, nothing in the DB. Revisit only with a deliberate decision about PCI scope.

### 4.7 The agent dock is the centrepiece of the design and is not in v0

The canvas leads with *"Your money, explained by an agent that does the work"*, a floating agent
dock on every screen, and a chat screen with drafted-payment cards.
**Resolution:** **not built.** v0 builds the seven seams that make it possible later
(`PROMPT.md` §7), not the layer itself. The dock is not rendered — a visible-but-dead assistant is
worse than an absent one. Worth noting the design already encodes the right constitution:
*"I drafted the transfer… nothing moves until you confirm"* is exactly seam 7.3's
`require_approval`.

### 4.8 Compliance badges in the login hero

The archive's hero shows `PSD2 / SCA · ISO 27001 · FGDB INSURED`.
**Resolution:** **removed.** This is a demo system with no licence and no deposit guarantee;
rendering FGDB insurance would be a false claim about a real Romanian scheme. Replaced by the
demo-system banner `PROMPT.md` §0 requires.

### 4.9 Dark theme is a runtime JS override of 9 variables

`applyTheme()` mutates `document.documentElement.style` directly.
**Resolution:** expressed declaratively in `tokens.css` for `prefers-color-scheme` **and** an
explicit `data-theme` attribute, so it works without JS and survives SSR. Theme choice is a user
preference — the same reversibility principle as hide-balances.

## 5. What was extracted

- `design/tokens.extracted.json` — full token set, `derived: true` on everything not in the
  archive, measured contrast ratios on every semantic colour.
- `apps/web/src/styles/tokens.css` — CSS custom properties plus the Tailwind v4 `@theme` block.
  **No component may contain a hex value**; the architecture test enforces it.

## 6. Open questions for the next session

1. **`/register` vs KYC.** The archive's 5-step KYC wizard is out of scope, but `/register` must
   still be a real route. Confirm: email + password + accept-terms, one step?
2. **Seven nav items or four?** v0 ships three "coming soon" entries. Confirm that is preferred
   over a shorter nav that grows later.
3. **Locale default.** Demo data is Romanian and `PROMPT.md` §6 says `ro` default — assumed
   confirmed unless you say otherwise.
