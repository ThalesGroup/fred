---
schema: 1
title: "Use underscore names for Fred built-in tools"
impact: none
configuration: none
configuration_reason: "Fred-owned tool identifiers and map instructions change without new configuration keys."
no_action_reason: "Existing dotted built-in declarations, SDK calls and Graph approval policies remain supported."
---
## Applicability

Fred deployments running agents that use built-in tool references.

## Prerequisites

The normal Fred release prerequisites apply.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. New agent code can import the same SDK constants for the
canonical underscore names.

## Validation

Run document search through a Graph or ReAct agent that declares the search
tool. The run should show `knowledge_search` and return grounded snippets.

## Rollback

Use the normal rollback procedure. Existing runs and traces retain their
recorded tool names.

## Limitations

New Graph events use the underscore identifiers. Historical events keep the
names recorded at the time, so trace filters may see both spellings. The
aliases cover Fred's historical built-ins. MCP and custom tool identifiers
follow their own contracts. Graph deployments with custom tool invokers
can override `ToolInvokerPort.has_exact_handler` to identify exact custom
registrations. If the invoker cannot report them, an explicitly declared
underscore name can still select the original custom handler. Declare and
invoke the dotted built-in reference to use that built-in in the same Graph.
