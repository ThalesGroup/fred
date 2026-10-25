## Context

`ManagedChatPage` disables the composer while `waitResponse` is true. `useChatSse` owns one abort controller and one active SSE request. ReAct and Deep use LangChain agent middleware; a `before_model` hook runs after a completed tool batch and before the next model call. Runtime history currently inserts the user message only at turn start.

## Goals / Non-Goals

**Goals:** Try the full interaction locally with a small, removable implementation. Preserve tool-call/result adjacency and report delivery only when the model-boundary hook consumes a message.

**Non-Goals:** Durable queueing across page reload or runtime replicas, Graph agent injection, command/attachment injection, and modifying an already dispatched parallel tool batch.

## Decisions

1. Keep the ordinary pending list in the managed chat hook, scoped to one session. Capture text on submit and show a compact disclosure panel above the composer, following the existing `write_todos` presentation. Each message stays on one line with an ellipsis. Use the composer's `+` menu pattern for per-message edit and delete actions, with icons; label the immediate action `Steer` in English and `Réorienter` in French. Send one ordinary turn at a time after the active turn closes. Editing a row returns its text to the composer; removing it drops it. This avoids a new database table for the reversible UI trial.
2. Add a separate authenticated runtime request for immediate steering. The existing SSE request cannot receive browser input. The request validates session ownership and team execution permission, then offers a message to a process-local active-run mailbox keyed by session and agent. An absent mailbox rejects the offer and leaves the client row pending.
3. Add a ReAct/Deep root middleware hook before model calls. It consumes offered messages after any completed tool batch, appends them as `HumanMessage` state updates and emits a typed custom runtime event. The event acknowledges actual delivery to the frontend and is mapped to a user history row in stream order. No middleware is installed in Deep child agents.
4. A forced row remains in the client pending list until its matching delivery event. If the run ends first, it reverts to ordinary queue behavior. Repeated force requests use the same message id, and the process-local mailbox deduplicates that id. A row awaiting delivery is temporarily locked against edit/delete; ordinary queued rows remain editable/removable.

## Risks / Trade-offs

- [Different runtime replica receives the steering request] -> Runtime refuses it; the message stays pending. This is a local trial and must not be deployed with multiple replicas without a shared mailbox.
- [The model is already generating its final answer] -> No further model boundary occurs; the pending message starts the next turn.
- [SSE delivery acknowledgement is lost] -> The client cannot prove consumption. Keep the row pending and avoid automatic retry after an uncertain transport failure; surface the uncertainty to the user.
- [Human input pause or interrupted execution] -> Hold ordinary queue draining until the existing resolution path completes.

## Migration Plan

No data migration. Reverting the frontend and runtime changes removes the prototype; existing sessions and history remain readable.
