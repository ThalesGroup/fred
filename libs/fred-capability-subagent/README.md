# fred-capability-subagent

A Fred agent capability (`subagent`) that gives an agent one tool,
`run_subagent`, to delegate a self-contained task to **a fresh-context copy of
itself** and get the answer back on an ordinary tool-result line.

What the runtime does for it, and why: `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md`
§8.63-§8.68. What is still open: `docs/swift/rfc/SUBAGENT-CAPABILITY-RFC.md`.

## What it ships

- **Tool** `run_subagent(prompt)` — runs the calling agent again, same
  `agent_id`, same capabilities and config, with none of the parent's
  conversation. The prompt the parent writes is everything the child knows.
- **Config** `max_depth` (default 3, clamped to 1–5) — how many delegation
  hops deep the tool stays available.
- **Config** `prompt_mode` (`append` default, or `replace`) — how the parent's
  prompt reaches the child. `append` keeps the child's own agent template and
  carries framing + prompt as its user message; `replace` sends framing +
  prompt as the child's template layer
  (`AgentInvocationRequest.system_prompt`) with a fixed trigger as the user
  message, so the child inherits no persona, output language or business rule.
  Guardrails, tool descriptions and the output contract are kept either way.
  Both ship so they can be compared on real agents; picking the winner is the
  RFC's one remaining open question (§2), and the loser is deleted then.
- **Metric** `agent.subagent_turn_completed` — one KPI event per finished
  child, carrying its tokens. Dims, Grafana/PromQL, and why a query reading
  `agent.turn_completed` alone under-counts:
  `docs/swift/platform/OBSERVABILITY-AND-AUDIT.md` §3.1.

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

Depth bounds height, not width: nothing bounds fan-out (#2531). N children are
N full agent turns running concurrently in one pod.

## Registration

Installing this package IS the registration — the `fred.capabilities` entry
point in `pyproject.toml` points the fred-agents pod at `SubAgentCapability`.
It is wired into the pod as an editable path dependency of `apps/fred-agents`.

## Known limitations

Local/POC surface today:

- **Unbounded fan-out**, and the content cap is per child so it does not
  compose with it. Deliberate for the POC, to be settled with POC data — #2531.
- **No timeout, and the parent's SSE stream is silent** for a child's whole
  run — the keepalive belongs to the tier-2 UI pass (RFC §5).
- **Work that needs a human decision cannot be delegated.** No human is
  reachable inside a child, so approval-gated tools are hidden from its model
  and anything else that would gate is refused with an error tool result. Not a
  hang risk, but a real limit on what a child can be asked to do
  (`RUNTIME-EXECUTION-CONTRACT.md` §8.64).

## Dev

```
make code-quality   # ruff + format + type-check
make test           # offline unit tests
```
