# `tools`

Thin client over the MCP gateway. **No business logic.** This is the only path any agent has to
the backend — it exists so that "call a capability" is one function call, not a place to smuggle
in a shortcut around the capability registry.
