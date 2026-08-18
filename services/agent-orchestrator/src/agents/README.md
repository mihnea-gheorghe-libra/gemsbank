# `agents`

The five workers: `SupportAgent`, `InsightsAgent`, `OnboardingAgent` (all `read`),
`PaymentsAgent` (`money-moving`, proposal-only), `RiskAgent` (`read`, screens proposals).

Each worker gets an explicit objective, output schema and tool list from the orchestrator — no
worker decides its own scope. Read-only workers may run in parallel; `PaymentsAgent` and
`RiskAgent` run sequentially, single-writer. See the service README constitution, rules 1 and 6.
