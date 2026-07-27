# TURN-04 — turn history, tool-call, and parallelism policies are not safely bounded

- **GitHub issue:** dedicated issue not yet created
- **Priority:** P1
- **Verdict:** confirmed
- **Owner:** unassigned

## Production impact

The ReAct model-input window is hard-coded to 500 messages even though the
adjacent comment says it matches a legacy limit of six. Persisted checkpoints
remain untrimmed. The platform policy defaults to no tool-call cap, and shipped
agent definitions do not set one. Finally, `allow_parallel_calls` is declared
and rendered in policy summaries but is never consumed by the runtime.

Long sessions can therefore send large prompts repeatedly, increasing
time-to-first-token, gateway tokens, memory, and cost. Tool exploration has no
Fred-level default budget, while the declared parallelism control does not
actually determine execution behavior.

## Evidence

- `libs/fred-runtime/fred_runtime/react/react_tool_loop.py:49-51` says the
  window matches six messages but sets `_V2_MAX_HISTORY_MESSAGES = 500`.
- `libs/fred-runtime/fred_runtime/react/middleware/checkpoint_hygiene.py:61-90`
  trims only the model request, deliberately leaving the checkpoint unchanged.
- `libs/fred-sdk/fred_sdk/contracts/models.py:789-813` defaults
  `max_tool_calls_per_turn` to `None` and declares `allow_parallel_calls`.
- `libs/fred-runtime/fred_runtime/react/middleware/frame.py:114-126` enforces
  the tool limit only when it is set.
- Repository usage of `allow_parallel_calls` is limited to contracts,
  summaries, and tests; the runtime does not consume it.
- No shipped `apps/fred-agents` definition assigns
  `max_tool_calls_per_turn`.

## Minimal fix direction

Define measured budgets rather than another arbitrary constant: maximum model
input tokens/messages, checkpoint retention/compaction policy, maximum tool
calls per turn, and parallel tool-call concurrency. Make the SDK fields truthful
and enforce them consistently in ReAct, Deep, and Graph.

## Acceptance criteria

- A design-owned token/message budget is enforced before every LLM call.
- Checkpoint growth has an explicit retention or compaction strategy.
- Every production agent has an intentional tool-call budget or an explicitly
  approved exception.
- `allow_parallel_calls` either controls bounded execution or is removed from
  the public contract.
- Tests cover long conversations, repeated tool loops, parallel calls, and
  user-visible terminal errors when a budget is exhausted.
- Load results record input tokens, time to first token, memory, and tool-call
  counts by bounded runtime/model dimensions.

## Decision log

- **2026-07-26:** recorded P1 confirmed. This finding is about absent or
  ineffective bounds, not a claim that every turn reaches them.

## Resolution evidence

Not resolved.
