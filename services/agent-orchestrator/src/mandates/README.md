# `mandates`

Mandate *presentation* and lifecycle UX — creating, viewing, revoking a mandate from the user's
side. **Evaluation does not happen here.** An agent must not be able to evaluate its own
authority; that stays in `platform/policy/` (seam 3) in `apps/api`, which is the only place a
mandate verdict is produced.
