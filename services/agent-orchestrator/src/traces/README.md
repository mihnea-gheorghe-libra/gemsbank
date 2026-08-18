# `traces`

Run traces, spans, and token/cost counters, written to `agent_runs` (seam 7 extended). Every trace
shares the `correlation_id` of the effects it caused, so an agent-initiated transfer is
reconstructable end to end: plan, capability calls, policy verdict, posting, confirmation — one
query, one id.
