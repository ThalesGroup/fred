## Why

When a Graph agent's process dies mid-run, its checkpoints are already persisted, but
FRED never continues from them. The next user message builds a fresh turn and LangGraph
starts again at `START` (`graph_executor.py` `_graph_input`), and `build_turn_state`
resets every business field that is not a declared carry field. The same capture,
retrieval and model generation then run again and can produce a different result. That
blocks agents with an important business commit in a step, such as a published migration
plan (GitHub issue #2892). In addition, LangGraph's default `"async"` durability lets the
next step start before the previous step's checkpoint is persisted.

LangGraph already supports both missing pieces: synchronous durability, and continuing a
thread from its last checkpoint with `astream(None, config)`. This change uses them and
lets the user choose, explicitly, whether to continue or restart.

## What Changes

- Graph agents run with `durability="sync"`: a step's checkpoint is persisted before the
  next step starts. This applies to every Graph agent; there is no SDK flag.
- A Graph thread whose latest checkpoint still has nodes to run, with no pending HITL
  interrupt, is an **interrupted execution**: the run died without ending. A run that
  ends in a live process, including a node failure or a step-limit stop, clears its
  pending tasks (`aupdate_state(config, None, as_node=END)`), so only a lost process
  leaves an interrupted execution behind.
- A new turn on a thread with an interrupted execution no longer restarts it silently.
  The runtime emits a new `execution_interrupted` runtime event and ends the response.
  The event carries a `HumanInputRequest` (stage `execution_interrupted`, choices
  `continue` and `restart`, naming the interrupted step) and an opaque `interruption_id`.
  The turn writes no history and no turn KPI.
- `RuntimeExecuteRequest` gains `interrupted_action` (`"continue"` or `"restart"`) and
  `interruption_id`:
  - `continue` resumes the interrupted step with `astream(None)`. It takes the existing
    durable single-use HITL claim, keyed by the interruption. A stale or unknown
    `interruption_id` is rejected.
  - `restart` runs the new turn exactly as today.
- Frontend: the chat renders `execution_interrupted` with the existing `HitlPrompt`
  component and restores the user's draft in the composer. A choice sends
  `interrupted_action`. After the user presses Stop, the next message in that session
  sends `restart` automatically.
- Existing HITL resume, ReAct and Deep agents are unchanged. On a non-Graph agent,
  `restart` is ignored and `continue` is refused because there is nothing to continue.

## Capabilities

### New Capabilities

- `interrupted-graph-execution`: synchronous step durability for Graph agents, detection
  of a crash-interrupted execution, and the explicit user choice to continue it from its
  last checkpoint or restart.

### Modified Capabilities

None.

## Impact

- SDK contracts (`fred-sdk`): `RuntimeEventKind.EXECUTION_INTERRUPTED`, a new
  `ExecutionInterruptedRuntimeEvent`, `ExecutionConfig.interrupted_action` and
  `interruption_id`, and two optional fields on `RuntimeExecuteRequest` with relaxed
  input validation for `continue`. All are additive; older clients keep today's
  behaviour except that a turn on an interrupted Graph thread is answered with the new
  event.
- Runtime (`fred-runtime`): `graph/graph_executor.py` (durability, detection, continue,
  clearing tasks when a live run ends) and `app/agent_app.py` (request plumbing, claim,
  skipping history and KPIs for the interrupted outcome).
- No new table, no Alembic migration. The claim reuses `checkpoint_hitl_claim` with a
  dedicated key prefix.
- Frontend: regenerated runtime client, `useChatSse.ts` and `useManagedChat.ts`
  (event handling, draft restore, Stop memory), and `ConversationThread.tsx` to render
  the `HitlPrompt`.
- Performance: one awaited checkpoint write per Graph step, small next to model calls.
  It is reviewed with `fred-performance-reviewer`.
- Docs: a dated entry in `RUNTIME-EXECUTION-CONTRACT.md` §8, `COMPONENT-UX.md`, and a
  migration note.
- Out of scope, possible follow-ups of #2892: lease-based owner recovery, an
  external-effect outcome journal, ReAct/Deep, showing the prompt when a conversation
  loads, and recovery of the crashed turn's own user message.
