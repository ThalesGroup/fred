# Agent Scope Context Reset

> **Architecture note — production branch only.**
> This mechanism was designed for the stateful v2 agent architecture (SQL checkpointer,
> agent cache, `RuntimeContext` binding at activation time). The agentic-pod branch
> introduces fully stateless agents with no cache and no SQL checkpointer. The problem
> this solves still exists there, but the solution will need to be reinvented to fit
> that architecture. Do not port this implementation blindly.

## Problem

V2 agents in the current production architecture are **activated once and cached**. At
activation time, the agent's tools are bound to the `RuntimeContext` in effect at that
moment — including `selected_document_libraries_ids`, `search_rag_scope`, and related
scope fields. This binding is frozen for the lifetime of the cached agent.

The LangGraph SQL checkpointer carries the full conversation state (including prior
tool calls and their results) across turns. When the user changes their library scope
mid-session, two things go wrong simultaneously:

1. **Tools query the wrong scope.** The tool invoker still uses the binding context
   from the original activation, so `knowledge.search` queries the old library set.

2. **The LLM does not re-invoke tools.** The checkpoint contains prior tool call/result
   pairs. The LLM sees "I searched lib-A → got result X" and reasons from that cached
   result rather than calling the tool again with the new scope.

The scope change is invisible to the LLM — it lives in `RuntimeContext` metadata that
is never part of the message stream.

## What is stored and where

After every exchange, `_attach_runtime_context()` in `session_orchestrator.py` stores a
sanitized `RuntimeContext` snapshot on every `assistant/final` message in the history
store. The fields that define "scope" for this purpose are:

- `selected_document_libraries_ids`
- `search_rag_scope`
- `include_session_scope`
- `include_corpus_scope`

This means the previous turn's scope is always available by reading the last
`assistant/final` message from the history store — no new persistence is needed.

## Solution implemented (production branch)

At the start of each turn, before the agent is invoked, the orchestrator:

1. Computes a **scope fingerprint** of the current `RuntimeContext`.
2. Reads the **stored fingerprint** from the last exchange's `assistant/final` message
   metadata (already in the history store).
3. If the fingerprints differ, it:
   - Calls `agent.streaming_memory.adelete_thread(session_id)` to wipe the SQL
     checkpoint for this session.
   - Forces a cache miss (`is_cached = False`) so the agent re-activates with the new
     `RuntimeContext` as its binding.
   - Allows `_restore_history()` to run, restoring conversation text context.

This ensures the re-activated agent binds tools to the correct (new) scope, and the
fresh checkpoint contains no stale tool results.

## Known residual limitation

After a scope reset, `_restore_history()` still injects prior `tool_call` and
`tool_result` messages into the restored history. The LLM can therefore still see and
reason from old tool results in the conversation context. In practice the re-activated
agent's tools will use the correct scope for any new calls, but the LLM may not
spontaneously re-invoke tools for the same question if it remembers a prior answer.

A follow-up improvement is to pass `skip_tool_messages=True` to `_restore_history()`
when triggered by a scope reset. The loop already distinguishes `Channel.tool_call` and
`Channel.tool_result`, so the filter is a one-liner. This was deferred as a second-order
concern.

## Why this needs reinvention on the new architecture

In the agentic-pod branch, agents are **fully stateless**: no activation cache, no SQL
checkpointer, no frozen tool binding. The scope-change problem still exists — the LLM
can still shortcut tool calls by reasoning from prior results in the message history —
but the solution space is different:

- There is no checkpoint to delete.
- There is no cache to evict.
- Tool binding happens per-turn, so problem (1) above disappears automatically.
- Only problem (2) remains: the LLM reasoning from stale results in the message window.

The right approach there is likely one of:
- Stripping `tool_call`/`tool_result` messages from the restored window when scope
  changes (the `skip_tool_messages` follow-up above, applied unconditionally on reset).
- Injecting a synthetic message signalling the scope change to the LLM.
- Keeping tool results out of the restored window entirely (always re-run tools).

## Touch points (production branch)

| File | Role |
|---|---|
| `agentic_backend/core/chatbot/session_orchestrator.py` | Detection logic + reset trigger |
| `agentic_backend/core/agents/v2/runtime_support/sql_checkpointer.py` | `adelete_thread()` — no change needed, already existed |
| `agentic_backend/core/agents/runtime_context.py` | `RuntimeContext` fields — no change needed |
