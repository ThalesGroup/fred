## Context

`ManagedChatPage` disables the composer while `waitResponse` is true. `useChatSse` owns one abort controller and one active SSE request. ReAct and Deep use LangChain agent middleware; a `before_model` hook runs after a completed tool batch and before the next model call. Runtime history currently inserts the user message only at turn start.

## Goals / Non-Goals

**Goals:** Support the interaction across runtime replicas with the existing shared SQL engine. Preserve tool-call/result adjacency and report delivery only when the model-boundary hook consumes a message.

**Non-Goals:** Browser queue persistence across page reload, exactly-once recovery after a process dies between model-state injection and its acknowledgement, Graph agent injection, command/attachment injection, and modifying an already dispatched parallel tool batch.

## Decisions

1. Keep the ordinary pending list in the managed chat hook, scoped to one session. Capture text on submit and show a compact disclosure panel above the composer, following the existing `write_todos` presentation. Each message stays on one line with an ellipsis. Use the composer's `+` menu pattern for per-message edit and delete actions, with icons; label the immediate action `Send` in English and `Envoyer` in French, using Fred's shared secondary tonal button at its `2xs` size and `spacing-2xs` between rows. Send one ordinary turn at a time after the active turn closes. Editing a row returns its text to the composer; removing it drops it. This avoids a new database table for the reversible UI trial.
2. Add a separate authenticated runtime request for immediate steering. The existing SSE request cannot receive browser input. Use one SQL-backed active-turn row per session, with an ordered bounded JSON message list, a turn id, owner/agent/team identity, state and a renewable lease. The stream and steer request carry the same client-generated turn id so a late request cannot enter a later turn. An absent or stale active row rejects the offer and leaves the client row pending. Reuse `PodApplicationContext`'s existing async SQL engine and connection pool; no per-request engine or new service. The session/history tables describe durable conversation data rather than transient in-flight delivery, so this row has a distinct lifecycle and merits one dedicated table.
3. Add a ReAct/Deep root middleware hook before model calls. It consumes offered messages after any completed tool batch, appends them as `HumanMessage` state updates and emits a typed custom runtime event. The event acknowledges actual delivery to the frontend and is mapped to a user history row in stream order. No middleware is installed in Deep child agents.
4. A forced row remains in the client pending list until its matching delivery event. If the run ends first, it reverts to ordinary queue behavior. Repeated force requests use the same message id, and the shared row deduplicates that id under a transaction lock. A row awaiting delivery is temporarily locked against edit/delete; ordinary queued rows remain editable/removable.
5. Before emitting `awaiting_human`, mark the row paused under its turn id and keep undelivered messages in SQL. A matching HITL resume, even on another replica, takes over the paused row before the next model boundary, including when the prior SSE stream has not finished closing. An active resumed row rejects a competing resume; the prior stream's turn id fences its late cleanup. Reject new offers while paused and discard the inactive entries if an unrelated ordinary turn starts. Final completion clears the row. Expired active leases reject offers; a process failure with uncertain acknowledgement remains visible as uncertain to the client.

## Risks / Trade-offs

- [Different runtime replica receives the steering request or HITL resume] -> Both read the shared row; delivery occurs on the executing replica at its next model boundary.
- [The model is already generating its final answer] -> No further model boundary occurs; the pending message starts the next turn.
- [SSE delivery acknowledgement is lost] -> The client cannot prove consumption. Keep the row pending and avoid automatic retry after an uncertain transport failure; surface the uncertainty to the user.
- [Human input pause or interrupted execution] -> Hold ordinary queue draining until the existing resolution path completes. An offered message remains available to the matching resume until a model boundary consumes it.

## Migration Plan

Add one runtime migration for the shared steering row. Deploy the migration before updating runtime replicas. Reverting the frontend and runtime changes leaves existing sessions and history readable; the steering table can be removed with the migration downgrade.
