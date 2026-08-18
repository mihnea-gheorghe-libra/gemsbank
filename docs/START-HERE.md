# How to use this bundle

Five files. Drop them into an empty repo, then hand the repo to Claude Code in VS Code.

```
gems-bank/                     ← new empty repo
├─ PROMPT.md                   ← rename PROMPT_CLAUDE_CODE.md to this
├─ CLAUDE.md                   ← Claude Code reads this automatically every session
├─ docs/
│  ├─ ARCHITECTURE.md
│  ├─ REFERENCES.md
│  └─ diagrams/
│     ├─ c1-context.mmd
│     ├─ c2-containers.mmd
│     ├─ c3-backend-modules.mmd
│     ├─ erd-core.mmd
│     ├─ seq-transfer.mmd
│     ├─ state-payment.mmd
│     ├─ agents-orchestration.mmd
│     └─ seq-agent-payment.mmd
└─ design/
   └─ export/                  ← unzip the Claude Design HTML archive here BEFORE Phase 0
```

## Opening message to Claude Code

> Read `PROMPT.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/REFERENCES.md` and every file in
> `docs/diagrams/`. Summarise back to me: the v0 scope, the seven agent seams, and anything in
> those documents you think is wrong or under-specified. Then execute **Phase 0** only.

Then one phase per session. Seven phases, 0 through 6.

## Before Phase 0

Put the Claude Design export in `design/export/`. If it is a `.zip`, unzip it there. If you do not
have it yet, say so — the prompt tells Claude Code to build with neutral tokens and flag the gap
rather than inventing brand colours, so nothing blocks.

## Viewing the diagrams

All eight `.mmd` files were syntax-validated against the Mermaid parser. To read them:

- **VS Code**: install the *Markdown Preview Mermaid Support* or *Mermaid Editor* extension.
- **GitHub**: renders `.mmd` in Markdown code fences; embed with ` ```mermaid ` if you want them
  inline in `ARCHITECTURE.md`.
- **mermaid.live**: paste the file contents.

Colour convention across the diagrams: **blue = built in v0**, **green = the money core**,
**dashed grey = scaffolded but empty**, **amber = a human in the loop**.

## Where to change things

| You want to… | Edit |
|---|---|
| Swap Python/FastAPI for a TS backend | `PROMPT.md` §2 — only `apps/api` changes, the schema and hexagonal split port over |
| Add or remove a v0 feature | `PROMPT.md` §4 — and update the Definition of Done |
| Change the data model | `docs/diagrams/erd-core.mmd` first, then `ARCHITECTURE.md` §4 |
| Change how the agent layer will work | `ARCHITECTURE.md` §6 + `agents-orchestration.mmd` — read `REFERENCES.md` first |
| Loosen a rule | `CLAUDE.md`. Be honest with yourself about which one and why. |

## The one thing not to compromise on

The seven seams in `PROMPT.md` §7. They are cheap now — an actor field, a bus, a policy call, an
audit row, an outbox row, a registry decorator, a correlation id. They are expensive later,
because retrofitting them means editing the money code, which by then will be the part you least
want to touch. Everything else in this design is negotiable.
