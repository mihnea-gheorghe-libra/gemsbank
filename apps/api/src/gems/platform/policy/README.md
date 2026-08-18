# Seam 3 — Policy engine

```python
verdict = await policy.evaluate(command, actor)   # allow | deny | require_approval
```

Runs **before every command**, inside the bus. There is no command that skips it.

## What it checks

Per-transaction limit, daily limit, currency allowed, beneficiary allowed, actor allowed.

## v0 behaviour

Static per-user limits, read from config. `require_approval` routes to the step-up stub in
`identity`. That is all — one rule set, no dynamic evaluation.

## What it becomes

The same interface evaluates **agent mandates**: scope (which capabilities), per-transaction and
per-period caps, beneficiary allowlist, validity window, revocation. The `mandates` table ships in
the first migration with the right columns and **zero rows**.

That shape is not invented here. It is the convergent answer across Google's AP2 mandate envelope
(donated to the FIDO Alliance in 2026), Visa's Trusted Agent Protocol and Mastercard's Agent Pay:
authority that is **scoped, capped, time-bounded, revocable and attributable**. See ADR 0003 and
`docs/REFERENCES.md`.

## The rule that makes this a security boundary

**Limits are enforced here, server-side. Never in a prompt.**

All model input is untrusted; prompt injection is assumed. A cap that a language model can be
talked out of is not a cap. When the agent layer lands, the policy engine is the thing standing
between a persuasive input and someone's money — which is why it must already be on the critical
path of every human transfer, tested by real traffic, before an agent ever depends on it.

## Rules

- `evaluate` is pure with respect to the DB write — it reads, it does not mutate.
- A `deny` carries a machine-readable reason code. "Computer says no" is not an error message.
- Adding a new command means deciding its policy. There is no default-allow.
