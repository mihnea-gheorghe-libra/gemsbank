# `alembic/versions`

Migration files. **Explicit only** — never trust `alembic revision --autogenerate` without
reading the diff line by line (CLAUDE.md). Alembic cannot see a `CHECK` constraint's intent or a
trigger's purpose; it will cheerfully propose dropping one it does not understand, and the
constraints in this schema are the product (ADR 0002).

The first migration is the one that matters most: full schema per `docs/diagrams/erd-core.mmd`,
including the empty `mandates` and `agent_runs` tables (ADR 0003) and the DB-level balance
constraint (ADR 0002).
