# `apps/web`

The GEMS web client. Currently one screen: the onboarding wizard at `/register`.

## Running it

There is no build step and no `npm install`. The API serves this folder as static files:

```
docker compose up --build
open http://localhost:8000/app/
```

React 18 and Babel standalone load from unpkg; `<script type="text/babel">` transforms the `.jsx`
files in the browser. Scripts execute in the order `index.html` lists them, and each file attaches
its exports to the `window.GEMS` namespace — that ordering is the module graph, so adding a file
means adding a `<script>` tag in the right place.

**This is a stopgap, not the target.** `docs/ADR/0004` and `PROMPT.md` §2 specify Next.js 15. The
component boundaries, the token layer and `src/lib/api/client.js` were written to port across unchanged;
what changes is the bootstrap and the namespace pattern. Record the migration as an ADR when it
happens.

If unpkg is unreachable from your network, download the three UMD bundles into `vendor/` and point
the three `<script src>` tags at them.

## Layout

```
index.html                     shell: stylesheet + script order
src/styles/tokens.css          design tokens — the only place a hex value may appear
src/styles/components.css      .btn .input .plate .tag — token references only
src/styles/onboarding.css      screen-01 layout
src/messages/{en,ro}.js        user-facing strings; no string is hardcoded in a component
src/lib/i18n.js                locale resolution + t()
src/lib/api/client.js          the only module that calls fetch()
src/components/ui/             Plate, Button, Field, TextInput, Tag, ErrorNote
src/components/onboarding/     StepRail, AgentPanel, one component per step
src/app/(auth)/register/       RegisterPage — owns state and orchestrates the flow
src/app/bootstrap.jsx          createRoot
```

The `(app)/` and `(auth)/` folders keep their Next.js route-group names so the tree still matches
`PROMPT.md` §5 and `docs/DESIGN_NOTES.md`.

## Accessibility

Labelled inputs, a real `<form>` per step, `aria-current="step"` on the rail, arrow-key and
backspace navigation across the OTP boxes, `role="alert"` on errors, visible focus rings from
`tokens.css`, and `prefers-reduced-motion` honoured. The archive's fixed `1440×900`
`overflow:hidden` shell is dropped — it breaks zoom and reflow (WCAG 2.2 AA 1.4.10).
