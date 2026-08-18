# `/login`

Email + password, Argon2id. **Not** the design archive's 4-digit PIN pad — see
`docs/DESIGN_NOTES.md` §4.4 for why, and where the PIN composition actually gets reused (the
step-up challenge).

Server Component shell, Client Component form. Access token in memory; refresh token in an
httpOnly cookie — never `localStorage`.
