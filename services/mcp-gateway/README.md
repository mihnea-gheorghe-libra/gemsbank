# `mcp-gateway` — designed here, built nowhere

**Status: no code. Folder reserved.**

## Purpose

Exposes the backend to the agent layer as MCP tools. It is the only thing an agent may talk to,
and it is deliberately thin.

## The one rule

**The tool list is generated from the capability registry (seam 6) and from nothing else.**

Not from route introspection. Not from a hand-maintained YAML. Not from "everything public on the
application services". From the registry, whose entries are typed, named, scoped and classified by
side effect.

The consequence is the security property: **an agent cannot call something that is not
registered.** Registration is a deliberate act by a person, and the gateway has no mechanism to
call anything else. That is why this service must stay thin — every piece of logic added here is a
place where the generated tool list could diverge from the registry.

## What it does

1. Reads the capability registry.
2. Emits MCP tool definitions: name, input schema, output schema, description.
3. Checks the caller's scope against the capability's required scope.
4. Forwards the call. Returns the result.

## What it must never do

- Add a tool not in the registry.
- Relax an input schema "to make the model's life easier". A model that cannot produce a valid
  input should fail loudly, not be handed a looser contract.
- Execute a `money-moving` capability. Those return **proposals**; execution goes through the
  command bus with a policy verdict.
- Hold credentials for more than one actor at a time, or act without an `on_behalf_of`.

## Depends on

`apps/api`'s capability registry. Nothing else.
