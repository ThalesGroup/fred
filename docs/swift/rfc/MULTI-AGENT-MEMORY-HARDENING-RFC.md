# RFC: Multi-Agent Memory Hardening

**Status**: Proposed

**Tracks**: MEMORY-02, MEMORY-03, MEMORY-04, MEMORY-05

**Current design**: [`../design/MULTI_AGENT_MEMORY.md`](../design/MULTI_AGENT_MEMORY.md)

## Summary

MEMORY-01 phases A-E shipped the core conversational memory contract. A code
audit confirmed four remaining hardening gaps before the feature should be
treated as fully closed:

- checkpoint state is session-scoped, not agent-scoped;
- remote agent invocation still uses a legacy request payload;
- local agent invocation still builds the private execution request directly;
- TeamAgent history append does not enforce the configured history cap.

This RFC narrows the remaining work into small implementation slices. It does
not reopen the shipped SDK memory contract.

## Current Findings

### MEMORY-02 - Agent-Scoped Checkpoint Isolation

Graph execution currently derives the checkpoint key from `ExecutionConfig` or
runtime `session_id` and writes LangGraph checkpoints with `checkpoint_ns=""`.
ReAct execution maps `ExecutionConfig.session_id` to LangGraph `thread_id`
without an agent namespace.

Result: two agents sharing one public session may load or overwrite the same
completed or pending checkpoint state. This is especially risky for TeamAgent
and callee agents, because both can run inside the same user conversation.

### MEMORY-03 - Remote Execute-Contract Convergence

`RemoteSseAgentInvoker` currently sends:

- `agent_id`
- `message`
- `context`
- optional `invocation_turns`

The public runtime execution contract uses `RuntimeExecuteRequest` shape:

- `agent_id` / `agent_instance_id` as applicable
- `input`
- `runtime_context`
- `invocation_turns`

Result: the remote agent-to-agent path preserves prior turns but remains on a
legacy payload shape.

### MEMORY-04 - Local Execution Projection Convergence

`LocalRegistryAgentInvoker` still hand-builds `_AgentExecuteRequest` with
`message`, `context`, and `invocation_turns` instead of projecting through the
same public `RuntimeExecuteRequest` bridge used by HTTP execution.

Result: local and HTTP execution can drift when execution metadata changes.

### MEMORY-05 - Team History Cap

`TeamAgent.build_completed_state` appends the new `ConversationTurn` to
`state.conversation_history` but does not truncate the result to
`conversation_history_max_turns`.

Result: carry-forward and invocation seeding are capped, but completed TeamAgent
state can grow past the configured limit.

## Proposed Direction

### F.1 Agent-Scoped Checkpoint Isolation

Keep `session_id` as the public conversation identity. Add an internal
agent-scoped checkpoint namespace for LangGraph persistence:

- use `thread_id = session_id`;
- use `checkpoint_ns = <agent scope>`;
- derive agent scope from the executing managed `agent_instance_id` when
  available, otherwise from the SDK `agent_id`;
- use the same derivation in GraphRuntime and ReActRuntime;
- preserve explicit `checkpoint_id` resume lookup inside the same namespace.

This uses existing LangGraph checkpoint semantics and avoids encoding multiple
concepts into `thread_id`.

Acceptance tests:

- two graph agents sharing one `session_id` do not share completed state;
- a TeamAgent and callee agent sharing one `session_id` do not bleed memory into
  each other;
- HITL resume still loads the expected checkpoint for the same agent namespace;
- checkpoint deletion or purge behavior is reviewed for namespace awareness.

### F.2 Remote Execute-Contract Convergence

Make `RemoteSseAgentInvoker` build and send the public runtime execute shape.
The remote endpoint should receive the same execution fields as local HTTP
execution, including `input`, `runtime_context`, and `invocation_turns`.

Acceptance tests:

- remote invoker payload matches `RuntimeExecuteRequest`;
- `prior_turns` still arrive as callee `invocation_turns`;
- legacy `message` / `context` payload usage is removed from the remote invoker.

### F.3 Local Execution Projection Convergence

Make `LocalRegistryAgentInvoker` construct a `RuntimeExecuteRequest` and reuse
`_to_internal_request(...)` or its direct successor. Keep `_AgentExecuteRequest`
as the single temporary private bridge until it can be removed entirely.

Acceptance tests:

- local invoker preserves `prior_turns`;
- local and HTTP projections produce equivalent internal execution metadata;
- invocation scope narrowing still applies before callee execution.

### F.4 Team History Cap

Apply the same oldest-first truncation rule after TeamAgent appends the new
turn:

- append the new `ConversationTurn`;
- truncate to the last `conversation_history_max_turns` entries;
- keep order oldest-first.

Acceptance tests:

- appending below the cap preserves all turns;
- appending at the cap keeps exactly `conversation_history_max_turns`;
- the oldest turn is discarded first;
- `conversation_history_max_turns = 0` behavior is either explicitly rejected or
  documented and tested.

## Recommended Branch Order

1. `fix/memory-agent-checkpoint-isolation`
2. `fix/remote-agent-runtime-execute-contract`
3. `refactor/local-agent-execute-projection`
4. `fix/team-memory-history-cap`

## Non-Goals

This RFC does not introduce:

- long-term memory or summarization;
- a new public memory API;
- callee-to-caller history merge;
- a replacement checkpointer;
- a change to public `session_id` ownership.
