# `lib/auth`

Session handling. Access token in memory, refresh token in an httpOnly cookie. **Never
`localStorage`** — CLAUDE.md rule, and the reason is XSS: a token in `localStorage` is readable by
any script that runs on the page, including an injected one.
