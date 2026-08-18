# `memory`

Conversation and run memory for the orchestrator. **Never a cache of balances or account state** —
money is always read live through a capability, never from memory, no matter how recent. A stale
balance shown as current is exactly the kind of quietly-wrong output a banking agent cannot afford.
