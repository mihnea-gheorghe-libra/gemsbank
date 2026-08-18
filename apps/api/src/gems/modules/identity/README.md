# `identity` — built in v0

**Status:** built.

## Scope

- Register, log in, refresh, log out.
- `GET /me`.
- Step-up (SCA) **port** defined; the v0 adapter is a stub that accepts a fixed dev code and logs
  the challenge.
- User preferences — v0 ships exactly one: `hide_balances`.

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
