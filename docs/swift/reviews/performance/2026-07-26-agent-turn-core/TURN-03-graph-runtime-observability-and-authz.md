# TURN-03 — Graph bypasses canonical LLM/tool observability and per-call authorization

- **GitHub issue:** dedicated issue not yet created
- **Priority:** P1
- **Verdict:** confirmed
- **Owner:** unassigned

## Production impact

ReAct and Deep route model/tool calls through platform middleware. Graph invokes
models and tools directly. Consequently Graph LLM work is measured as generic
`app.phase_latency_ms`, Graph tool work has no canonical
`agent.tool_latency_ms`, tool audit events are absent, and regular-user tool
calls do not reverify team access at the tool boundary.

This is both an operational and security divergence: Graph latency cannot be
compared reliably with ReAct/Deep in Grafana, and revoked access can remain
trusted for the whole Graph turn rather than being checked for each tool call.

## Evidence

- `libs/fred-runtime/fred_runtime/graph/graph_runtime.py:411-524` calls
  `resolved_model.astream` directly and times the phase with
  `app.phase_latency_ms`.
- `graph_runtime.py:526-612` follows the same generic timing path for structured
  model calls.
- `graph_runtime.py:614-790` invokes tools directly.
- The Graph runtime contains no use of `llm.call_latency_ms`,
  `agent.tool_latency_ms`, `emit_audit_log`, or
  `ToolObservabilityMiddleware`.
- `libs/fred-runtime/fred_runtime/react/middleware/tracing_kpi.py:103-123`
  emits the canonical ReAct/Deep LLM metric.
- `libs/fred-runtime/fred_runtime/react/middleware/tool_observability.py:213-315`
  performs the per-tool authorization, timer, failure counter, and audit events
  for ReAct/Deep.

## Minimal fix direction

Extract runtime-neutral model-call and tool-call boundary services/middleware,
then make ReAct, Deep, and Graph use those same chokepoints. Preserve Graph's
declared `asyncio.gather` fan-out, but apply authorization and telemetry inside
each individual operation.

## Acceptance criteria

- Every runtime emits the same canonical LLM and tool metrics through the
  resilient KPI sink.
- Every actually executed tool call emits start/completion/failure audit events.
- Every non-service-agent team tool call performs the agreed fail-closed
  authorization check.
- Tests exercise ReAct, Deep, and Graph rather than asserting the guarantee from
  one implementation.
- A mixed-runtime dashboard and 200-turn test expose comparable latency,
  failures, and authorization cost without high-cardinality labels.

## Decision log

- **2026-07-26:** recorded P1 confirmed. The previous platform document's
  “every tool invocation” claim was narrowed to the implementations that
  actually pass through the middleware.

## Resolution evidence

Not resolved.
