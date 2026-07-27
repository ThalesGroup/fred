# TURN-08 — runtime activation and ReAct compilation are repeated for every turn

- **GitHub issue:** dedicated issue not yet created
- **Priority:** P2
- **Verdict:** needs-load-test
- **Owner:** unassigned

## Production impact

Every request rebuilds runtime services, capability bindings, model wrappers,
the ReAct/Graph runtime, and the executor. ReAct ultimately calls LangChain
`create_agent` for every turn. Shared HTTP clients prevent transport churn, but
the graph/middleware/tool assembly and compilation cost is paid repeatedly.

This may be small compared with a remote LLM call, but it is directly on time to
first token and multiplies during a concurrency wave. Static inspection cannot
establish whether safe reuse is worth its lifecycle and request-isolation
complexity.

## Evidence

- `libs/fred-runtime/fred_runtime/app/agent_app.py:2486-2726` constructs
  per-turn contexts, services, capabilities, runtime, and executor, then
  disposes the runtime.
- `libs/fred-runtime/fred_runtime/react/react_runtime.py:600-748` activates
  tools and builds the executor for the current binding.
- `libs/fred-runtime/fred_runtime/react/react_runtime.py:780-847` delegates to
  the ReAct tool-loop builder.
- `libs/fred-runtime/fred_runtime/react/react_tool_loop.py:54-131` calls
  LangChain `create_agent`.
- LLM and Knowledge Flow HTTP clients are process-wide shared clients, so this
  finding does not allege a new transport connection per turn.

## Minimal fix direction

Instrument activation subphases first. If material, cache only immutable,
principal-independent compiled structure keyed by agent definition/version and
capability shape; keep binding, authorization, tokens, checkpoint context, and
request-scoped middleware state outside shared objects.

## Acceptance criteria

- Activation/build/compile duration is measured separately from authorization,
  MCP discovery, and LLM latency.
- A benchmark compares cold and warm turns at concurrency 1 and 200.
- Any reuse design proves no cross-user token, checkpoint, interceptor, tool,
  or baggage leakage.
- Cache invalidation covers agent definition and capability changes and states
  its per-pod/four-replica behavior.

## Decision log

- **2026-07-26:** recorded P2 `needs-load-test`; repeated construction is
  confirmed, but material latency is not.

## Resolution evidence

Not resolved.
