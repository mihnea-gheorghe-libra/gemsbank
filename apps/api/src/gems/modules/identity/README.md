# `identity` — built in v0

**Status:** built.

## Scope

- Register, log in, refresh, log out.
- `GET /me`.
- Step-up (SCA) **port** defined; the v0 adapter is a stub that accepts a fixed dev code and logs
  the challenge.
- User preferences — v0 ships exactly one: `hide_balances`.

## Onboarding (built)

Four steps, one aggregate: `KycCase`. The state machine lives in `domain/kyc.py` and is the only
thing that decides whether a transition is legal.

```
started --submit_document--> document_submitted --set_contact--> contact_provided
        --verify_code--> code_verified --complete--> completed
```

| Endpoint | Command | Notes |
|---|---|---|
| `POST /onboarding` | `StartOnboarding` | opens a case, returns `kycCaseId` |
| `POST /onboarding/{id}/document` | `SubmitIdentityDocument` | multipart; nothing binary is persisted |
| `POST /onboarding/{id}/contact` | `SetContact` | normalises, checks email is free, sends the code |
| `POST /onboarding/{id}/code/resend` | `ResendCode` | 30 s cooldown, 3 resends |
| `POST /onboarding/{id}/code/verify` | `VerifyCode` | 5 attempts, 5 min TTL |
| `POST /onboarding/{id}/complete` | `CompleteOnboarding` | creates the user |
| `GET /onboarding/{id}` | — | read model, no command |

Every write goes through `CommandBus.execute(command, actor, idempotency_key)` and, inside one
Mongo transaction, writes the state change, an audit row and an outbox event. The actor is
`system:public-onboarding` — nobody is authenticated yet, and the column already exists for the
day an `OnboardingAgent` drives the same commands.

**Failed code attempts are written outside the transaction.** The counter has to survive the abort
that the `ValidationError` causes, or a wrong guess would be free.

### Age eligibility

`ExtractedIdentity` carries a real `date` birth date, and `KycCase.submit_document` refuses a
document belonging to someone under `MINIMUM_AGE_YEARS` (18, `Settings.minimum_age_years`) with a
`not_eligible` error. The check runs at **document submission**, not at completion — the moment we
learn the date is the moment to refuse, and the case stays at `started` so the applicant can
upload a different document.

This is a **domain rule, not a policy-engine rule** (seam 7.3). Policy evaluates commands against
limits and mandates; eligibility to hold an account is intrinsic to the KYC aggregate and must
hold regardless of who or what submits the command.

`age_in_years` compares `(month, day)` tuples, so a birthday today counts and 29 February counts
on 1 March in a non-leap year.

The demo extractor produces a minor for roughly **one file in eight**, deterministically from the
file hash. That is intentional: the rejection path has to be reachable without special input. The
same file always yields the same answer, which is how real OCR behaves — upload a different file
to get a different identity.

### No biometrics, no stored documents

There is no selfie step. The uploaded ID is read into memory, hashed to pick a synthetic identity
from a fixed list, and discarded — `adapters/document_extractor.py`. The CNP is masked to its
first four digits before it ever leaves that adapter. Real OCR plugs in behind the
`DocumentExtractor` port without touching the domain.

### Ports

`OtpSender`, `DocumentExtractor`, `PasswordHasher`, `KycCaseRepository`, `UserRepository`, `Clock`
— all in `application/ports.py`, all `Protocol`s, all wired in `composition.py`.

Without `RESEND_API_KEY` the OTP adapter logs instead of sending, and the API returns the code as
`delivery.devCode` so onboarding stays completable offline. That field is absent as soon as a real
API key is configured.

## Credentials

**Argon2id.** Short-lived access JWT plus a rotating refresh token stored server-side and
revocable — `sessions.refresh_token_hash` with `revoked_at`. Revocability is the point: a JWT you
cannot revoke is a credential you cannot take back.

Tokens live in memory or httpOnly cookies in the web app. **Never `localStorage`.**

Secrets come from env only. `.env` is never committed.

## The step-up port

```
identity.application.step_up.challenge(actor, action, context) -> Challenge
identity.application.step_up.verify(challenge_id, response) -> bool
```

Deliberately **device-and-channel agnostic** rather than SMS-shaped. The market brief's second
most-cited pain was painful re-authentication when changing phone or number, especially for the
diaspora — an interface that assumes "send an SMS to the registered number" bakes that pain in.
This one accommodates push, passkey or OTP as adapter choices.

PSD3/PSR keeps the two-factor SCA rule and newly permits two inherence factors, so the port must
not assume possession-plus-knowledge either.

v0's adapter is a stub. Real SCA is future work; the call site is already correct.

Sensitive operations route through it: transfers above a threshold, credential changes, adding a
beneficiary.

## The design conflict

The design archive authenticates with a 4-digit PIN. v0 uses email + password, and reuses the PIN
pad composition for the **step-up challenge** instead — which is where a 4-digit secret actually
belongs. See `docs/DESIGN_NOTES.md` §4.4.

## Public port

`identity.application`: `register`, `authenticate`, `refresh`, `revoke_session`, `get_user`,
`get_preferences`, `set_preferences`, plus the step-up port above.

## May depend on

`platform/` only. It is the module everything else is allowed to hold a foreign key to
(`identity.users`) — and the only one.
