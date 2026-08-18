# `components/status`

`StatusBanner` — the incident/status banner fed by `GET /system/status`. **Has no precedent in
the design archive** (`docs/DESIGN_NOTES.md` §4.5); composed from the archive's `.blueprint` plate
and the `warning` token.

Built because unannounced downtime with no proactive communication was the single most-cited user
frustration in the market brief. Dismissible, but reappears on the next incident — dismissal is
per-incident, not permanent.
