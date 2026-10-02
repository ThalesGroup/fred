## Context

The motivation is in proposal.md. The relevant current behaviour of the Graph path:

- `GraphExecutor._run` calls `self._compiled.astream(graph_input, ...)` without
  `durability`. LangGraph 1.2.x then defaults to `"async"`: a step's checkpoint is written
  while the next step already runs.
- `GraphExecutor._graph_input` returns `Command(resume=...)` for a HITL resume. In every
  other case it returns a full state built by `build_turn_state`, so LangGraph starts at
  `START`. Only declared carry fields survive from the previous state.
- A node failure without `on_error`, a `GraphRecursionError` and any other exception end
  the run in the same process. Each of them can leave the thread's latest checkpoint with
  pending `next` nodes.
- A client disconnect or the Stop control cancels the stream (`CancelledError`, which is
  not an `Exception`). The run ends, and its response, history and KPIs are dropped
  (contract §8.89).
- `agent_app` admits a HITL resume through a read-only validation, then a durable claim
  (`_claim_hitl_resume_before_invocation` over `checkpoint_hitl_claim`), taken just
  before invoking the executor. The Graph branch keys the claim by
  `executor.thread_id(execution_config)`.
- The frontend renders HITL requests with `HitlPrompt`, which is driven by a
  `HumanInputRequest`. It can already restore a draft into the composer
  (`onTurnRejected`).

A throwaway spike was run on `FredSqlCheckpointer` (SQLite file) with LangGraph 1.2.12,
using `Command(goto=...)` nodes `a → b → c` and `durability="sync"`. It was not committed.

| Case | Observed |
|---|---|
| Process killed (`os._exit`) inside `b` | A new process reads `next=('b',)`, no interrupts, no task error |
| `astream(None)` in that new process | Runs `b` and `c` only (`a` is not re-run) and completes |
| `b` raises | Leaves `next=('b',)` with a task error. `aupdate_state(cfg, None, as_node=END)` then gives `next=()` and keeps the values. |

## Goals / Non-Goals

**Goals:**

- Use only public LangGraph APIs: `durability`, `aget_state`, `astream(None, ...)` and
  `aupdate_state(..., as_node=END)`.
- Add no new persistent state and no migration.
- Reuse the HITL request model, the HITL card and the HITL claim. The HITL protocol and
  its history semantics stay untouched.

**Non-Goals:**

- Automatic continuation, background recovery or retries. A continuation always comes
  from an explicit user choice.
- Owner leases, fencing a late writer, or an external-effect journal. Business
  idempotency of external commits remains the agent author's responsibility: fix the key
  in an earlier step and publish idempotently.
- ReAct and Deep agents.
- Showing the card when a conversation loads, and recovering the crashed turn's user
  message.

## Decisions

### D1. Sync durability for every Graph agent, without a flag

`astream(..., durability="sync")` is passed unconditionally in `GraphExecutor._run`.
LangGraph then awaits the step's checkpoint future before the next tick.

Alternative considered: an SDK opt-in such as `GraphWorkflow(durable=True)`. It was
rejected. The cost is one awaited database write per step, which is small next to model
calls. Every Graph agent benefits. A flag would add surface that everyone should enable
anyway. The latency effect is checked with `fred-performance-reviewer`.

### D2. "Interrupted" means the process was lost, not that the run failed

The executor reads the thread state that `_graph_input` already loads. The thread is
interrupted when all of the following hold:

- `snapshot.next` is non-empty;
- `snapshot.interrupts` is empty;
- the request is not a HITL resume.

For this test to mean "process lost", every run that ends in a live process must leave
`next` empty. In the `GraphRecursionError` branch, the generic `Exception` branch and the
"no completed state" branch, `_run` therefore calls
`await self._compiled.aupdate_state(thread, None, as_node=END)`. That is LangGraph's
public "clear all tasks" form. It keeps the channel values, so carry-forward for the next
turn is unchanged. The clearing is best-effort and logged. If it fails, the next message
offers `continue`, which re-runs the failed step, fails, and is then cleared: a degraded
but safe path.

The clearing is fenced to the failing run. Each run puts a `fred_graph_run` id in its
`configurable`, and LangGraph copies that id into the metadata of every checkpoint the
run writes. A run clears the thread only when the head is still the one it started from,
or carries its own run id. A head that another run has advanced keeps its pending steps.
The check covers a checkpoint saved but not yet streamed, which happens at the step
limit.

Cancellation is deliberately **not** cleared. A closed tab or a network loss looks like a
crash to the user and stays continuable. The deliberate Stop case is handled by the
client (D6).

Alternative considered: inspecting `snapshot.tasks[*].error`. It was rejected because it
does not cover the step limit, where pending tasks carry no error. It would also tie the
result to how LangGraph records failed writes internally.

### D3. Interruption identity

`interruption_id` is the first 32 hex characters of
`sha256(thread_id + "\0" + head_checkpoint_id)`. Here `head_checkpoint_id` comes from
`snapshot.config["configurable"]["checkpoint_id"]`.

- The identifier is opaque. It does not reintroduce `checkpoint_id` on the wire, which
  contract §8.86 removed.
- It changes as soon as the thread advances, so a stale `continue` is detected by
  recomputing it from the current head. No state is stored for this.
- The executor recomputes it on `continue`. A mismatch, or no interrupted execution,
  raises an execution error before anything runs.

### D4. The new event wraps a `HumanInputRequest`

The new type is
`ExecutionInterruptedRuntimeEvent(kind="execution_interrupted", request: HumanInputRequest, interruption_id: str)`.
Its request has these values:

| Field | Value |
|---|---|
| `stage` | `"execution_interrupted"` |
| `title` | English text naming the interrupted step: the node title, falling back to the node id. `__fred_complete__` is rendered as a generic "final step". |
| `choices` | `continue` and `restart` |
| `metadata` | `node_id` and `node_title` |
| `interrupt_id` | not set |

The frontend renders it with `HitlPrompt`. It uses localized strings for this stage and
takes the step name from `metadata`.

Alternative considered: emitting a real `awaiting_human` event and answering it through
`resume_payload`. It was rejected for three reasons:

- the HITL admission requires a pending LangGraph interrupt, and there is none;
- faking one would fabricate a human approval, which #2892 forbids;
- it would write HITL request/response rows into history.

### D5. Request plumbing and admission

- **`RuntimeExecuteRequest`** gains `interrupted_action: Literal["continue", "restart"] | None`
  and `interruption_id: str | None`. Validation:
  - `continue` requires `interruption_id` and forbids `resume_payload`; input may be
    empty;
  - `interruption_id` is only valid with `continue`;
  - `restart` keeps the ordinary input rule.

  The internal `_AgentExecuteRequest` and `_to_internal_request` mirror these fields.
  `ExecutionConfig` carries both fields to the executor.
- **Graph branch of `agent_app`.**
  - For `continue`, `GraphExecutor.interruption_id()` first validates the id read-only,
    so a stale id or a failed read leaves no claim. The existing claim helper is then
    called with `interrupt_id=f"continue:{interruption_id}"` on the agent's thread, and
    the claim is consumed after the stream. The executor re-checks the id after the
    claim, to cover races.
  - For a non-Graph executor, `continue` raises an execution error and `restart` is
    ignored.
  - Authorization runs before any of this, unchanged. The event is only produced inside
    the executor stream, which runs after `_authorize_and_resolve`.
- **`GraphExecutor._graph_input`** decides which mode applies:

  | Request | Thread interrupted? | Mode |
  |---|---|---|
  | `continue` | yes, with the matching `interruption_id` | `None` input (continue) |
  | none | yes | report the interruption |
  | `restart` or none | no | today's fresh-turn path |

  `_run` turns "report the interruption" into the event and returns. It runs no step and
  produces no final event.
- **`_stream` and the non-streaming `execute`.** When a payload of kind
  `execution_interrupted` is present, they skip `_emit_turn_completed` and
  `_write_turn_history`. A continued turn has no user message, so `_write_turn_history`
  writes no user row. Its assistant rows go into a fresh exchange.

### D6. Frontend

- `useChatSse` maps `execution_interrupted` to a new callback. `useManagedChat`:
  - restores the draft, reusing the `onTurnRejected` mechanism;
  - stores the request and `interruption_id`;
  - renders `HitlPrompt` in the thread with localized title, question and choices for
    this stage.
- **Continue** sends a turn with `interrupted_action: "continue"` and the
  `interruption_id`, with empty input and no new user bubble.
- **Restart** re-sends the same wire text and command with
  `interrupted_action: "restart"`.
- `send()` reports whether the turn started. Either choice puts the card back when its
  request never started (token, session write or preparation failure), as the HITL
  resume path already does.
- A set of session ids records which sessions the user stopped; switching sessions
  does not clear it. The next send in a stopped session adds
  `interrupted_action: "restart"`, and the session leaves the set when that turn starts.
- Types come from the regenerated runtime client. No hand-written duplicate is added.

## Risks / Trade-offs

- **[A run still executing elsewhere looks interrupted, because its pending steps
  are identical.]** A second tab or device can be offered Continue for a live run
  and execute the same step concurrently. Before this change, a second message
  already started a concurrent turn on the same thread. Mitigation: Continue needs
  an explicit click, and the single-use claim deduplicates continues. A liveness
  lease is the follow-up that would close this; it is not built here (#2892 owner
  recovery).
- **[Some callers cannot present the choice.]** `GraphExecutor.invoke`, child
  invocations and the OpenAI-compatible route therefore default to `restart`.
  Direct `/agents/execute` API clients receive the typed event and must answer it.
- **[Restart re-sends the same wire text and command, but not attachments.]**
  Attachments were cleared when the turn started.

- **[A continue that crashes again inside the same step leaves its claim `started` for
  that interruption, so a further `continue` is refused.]** A stale id or a failed
  pre-claim read no longer leaves a claim, but the claim stays single-use by design. The head checkpoint, and therefore `interruption_id`, only changes once a
  step completes. Mitigation: the refusal names the cause, and `restart` remains
  available. A lease-based claim is a possible follow-up.
- **[Threads left with pending tasks before deployment are offered `continue` after
  deployment]**, including threads that ended in a node failure. Mitigation: a continue
  re-runs the failed step. If it fails again, the thread is cleared and the next message
  behaves as before. This is documented in the migration note.
- **[The step re-run on `continue` repeats any side effect inside it.]** This is the same
  replay that today's restart already performs, and more. The authoring guidance is
  explicit: fix the key in an earlier step and commit idempotently.
- **[After a reload, the crashed turn's user message is missing from history]** (§8.89).
  Mitigation: the card names the interrupted step. Recovery of that message is a
  non-goal.
- **[The Stop flag is in memory only.]** A reload right after Stop forgets it, so the card
  appears. That is harmless, because `restart` is offered.
- **[The sync write adds latency per step.]** It is measured in the performance review.
  It is one write per step and is already performed today, only asynchronously.

## Migration Plan

- The change is additive on the wire. An old frontend sees `execution_interrupted` as an
  unknown event: the turn shows no answer. It needs the updated frontend to offer the
  choice, so the frontend and runtime ship in the same release.
- No operator action and no schema change. A migration note is required by repository
  policy.
- Rollback: revert the runtime and the frontend. Threads keep their checkpoints, and the
  next message restarts as before.
