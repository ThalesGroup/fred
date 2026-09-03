# fred-capability-subagent

A Fred agent capability (`subagent`) that gives an agent one tool,
`run_subagent`, to delegate a self-contained task to **a fresh-context copy of
itself** and get the answer back on an ordinary tool-result line.

Design: `docs/swift/rfc/SUBAGENT-CAPABILITY-RFC.md` (issue #2525).

## What it ships

- **Tool** `run_subagent(prompt)` — runs the calling agent again, same
  `agent_id`, same capabilities and config, with none of the parent's
  conversation. The prompt the parent writes is everything the child knows.
- **Config** `max_depth` (default 3, clamped to 1–5) — how many delegation
  hops deep the tool stays available.

The child is an ordinary agent turn: it runs concurrently with its siblings
(LangGraph's tool node runs one message's tool calls in parallel), keeps the
parent's `session_id` for KPI grouping, writes no history row of its own, and
runs without a checkpointer so it can never load or overwrite the parent's
state.

## Recursion is bounded where the tool is built

The runtime tells every capability how deep the current turn is
(`CapabilityContext.invocation_depth`, counted on a private attribute of the
invoker — never on the request, so a crafted invocation cannot reset it). At
`max_depth` this capability simply returns no tool, so a leaf child is never
shown a delegation it would only be refused. There is deliberately no second
limit in the runtime.

Depth bounds height, not width: **nothing bounds fan-out**. N children are N
full agent turns running concurrently in one pod, and
`max_tool_calls_per_turn` does not help — it maps to a per-graph-run limit and
a child is its own graph run, so the counter resets at every level.

## Registration

Installing this package IS the registration — the `fred.capabilities` entry
point in `pyproject.toml` points the fred-agents pod at `SubAgentCapability`.
It is wired into the pod as an editable path dependency of `apps/fred-agents`.

## Known limitations

Local/POC surface today — settle these before enabling it anywhere shared
(RFC §5.5, raised by this change's performance review):

- **Unbounded fan-out.** See above. One user message can launch enough
  concurrent child turns to exhaust the pod's shared connection pool, which
  fails *other users'* turns too.
- **The content cap does not compose.** It is per child; N children each under
  it still overrun the parent's history budget — after every one of them has
  been paid for.
- **No timeout, and the parent's SSE stream is silent** for a child's whole
  run (RFC §10).
- **Child turns emit no turn-level KPI**, so their token spend is counted
  nowhere (#2528).
- **Approval-gated (HITL) tools are not yet stripped** from a child's tool
  list, and a child has no checkpoint an interrupt could persist to (#2526).
  Until that lands, enable this only on agents with no approval-gated tools.

## Dev

```
make code-quality   # ruff + format + type-check
make test           # offline unit tests
```
