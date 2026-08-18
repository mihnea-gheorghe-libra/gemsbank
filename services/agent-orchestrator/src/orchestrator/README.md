# `orchestrator`

Lead agent: intent classification, planning, worker fan-out, aggregation, and the decide
answer-or-propose step. **Never calls the database or a module directly** — only workers, and
only through `tools/` (the MCP gateway client). See the constitution in the service README.
