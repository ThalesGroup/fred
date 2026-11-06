## Context

The runtime stores a complete turn's trace after the SSE stream, while the steering mailbox stores unconsumed text separately. `session_history` already has a per-session rank key and is the authoritative history read path. The browser groups adjacent tool calls/results into trace segments and starts a new visual segment at each user row. A pending user row therefore must be rendered outside canonical trace order until a model boundary is reached.

## Goals / Non-Goals

**Goals:** Keep one durable user-message identity across HTTP retries, SSE delivery, history reload, and a later ordinary turn. Assign one fixed provisional rank at receipt, and one definitive rank at incorporation. Preserve rank ordering of canonical trace and checkpoint recovery across runtime replicas.

**Non-Goals:** Steering an already running Graph turn, queuing attachments or commands, and canceling an in-flight tool call. The model cannot undo a tool call dispatched before the new message was sent.

## Decisions

### Store message state in `session_history`

Use a user/final row with nullable `message_id` and `delivery_state` columns, exposing these through `metadata.extras` on history reads. A unique `(session_id, user_id, message_id)` index and a `(session_id, user_id, delivery_state, rank)` index make retries and pending scans bounded. The provisional rank is a negative per-session sequence allocated in a transaction; canonical ranks remain nonnegative and increasing. A pending row has its own temporary `exchange_id`, replaced by the actual exchange at delivery, so legacy exchanges with empty IDs cannot absorb it. The browser orders only pending rows at the visible end by their provisional sequence. This reuses the existing history lifecycle and ownership model. A new queue table would recreate the current dual-source failure mode.

### Reserve canonical rank from the turn's trace sequence

At turn start, wait for the preceding turn's history commit and capture `MAX(canonical rank)+1`. A single rank allocator reserves positions for both SSE events and persisted trace rows. The stream sends these ranks with each ranked event, so the live browser and reloaded history use the same order. At the safe model boundary, a short tool-free model call answers the in-progress update. One `steered_assistant_message` event carries the pending user identities and the reply. Its consumer promotes the user rows and inserts the assistant row in one SQL transaction, then acknowledges persistence before ordinary model or tool work resumes. The turn writer reserves those ranks but skips their second insertion. Synthetic `tool_use` thoughts do not consume a canonical rank. Rank gaps from empty reasoning blocks remain allowed. A later pending message keeps its negative rank until its own boundary.

### Make the history write part of stream completion

Finish writing the collected trace before the SSE stream closes, instead of spawning the write after close. This makes the next turn's initial rank reliable and removes a race with a follow-up submission. The final SSE frame still arrives promptly; the close waits for persistence. The endpoint also writes history on an interrupted stream, preserving already visible trace where possible.

### Treat the model boundary as delivery, and reconcile checkpoints

The middleware reads pending rows in send order from shared SQL and injects stable LangGraph `HumanMessage.id` values after the completed tool batch. It makes one tool-free model call for the pending batch, then emits the combined delivery/reply event and waits for a run-scoped persistence receipt before the normal model call. If the model returns no visible text or an unexpected tool call, it retries once and then uses a localized plain acknowledgement through the same persistence path. Usage from both attempts is included in the turn total. The continuation model request includes the visible assistant reply followed by an ephemeral user-role instruction to resume the original task; this keeps the request valid for providers that reject a completed assistant message as the final input. That instruction is excluded from the checkpoint and chat history. A failed reply call or SQL transaction leaves the user rows pending. The assistant reply has an idempotent identity derived from the full ordered batch of user message IDs. On continuation, delivered user rows and assistant replies from the current exchange are reconciled with checkpoint messages in rank order. A crash between an external model call and checkpoint commit can replay that call, as with other runtime work; stable identities prevent duplicate history rows. Steering middleware is installed only for top-level executions whose event consumer persists and acknowledges ranked chat events; nested agent invocations and OpenAI-compatible streams have no such consumer.

### Continue a message that misses the boundary

After a completed turn with pending rows and no human-input hold, the open chat starts one ordinary turn using the oldest persisted pending message identity. The runtime reserves that exchange's opening canonical rank for the row and promotes it at the first model boundary. The opening ReAct/Deep checkpoint message carries the same stable ID, so a later HITL resume cannot inject it again. Graph execution has no such boundary hook, so a Graph fallback acknowledges the row at its first final answer or human-input pause. If the browser closes, opening the conversation restores this state from history and continues it. During a human-input pause before an ordinary fallback starts, the message remains pending until the matching continuation reaches a boundary.

### UI state follows the persisted row

The composer creates an optimistic in-thread message keyed by a UUID, calls the authenticated runtime endpoint, and reconciles its rank and state from the response. A small clock is shown for `pending` and disappears on delivery. History reload uses the durable state; no browser pending queue or queue disclosure remains. If the next-turn attempt fails, the clock becomes a retry control while the chat is idle. Retrying keeps the same message identity. A network uncertainty resolves by refetching the same message ID, not by creating another identity.

## Risks / Trade-offs

- [History persistence adds latency at stream close] -> Keep one batched write, measure the additional close time, and avoid a database call per trace token.
- [Pending rows may be received while a turn is finishing] -> Serialize promotion and trace persistence per session; a late row remains pending for the following ordinary turn.
- [Model call and SQL/checkpoint commits are not one transaction] -> Use stable IDs and reconcile pending state with checkpoint messages on continuation. External tool/model effects remain subject to the runtime's existing retry semantics.
- [Each in-progress update batch adds one model call] -> Generate one short reply for the batch without tools, then continue the original model decision; count both calls in turn usage.
- [Negative provisional ranks are not canonical order] -> Only rows explicitly marked pending use the bottom-of-thread presentation rule. All delivered and ordinary messages continue to sort by canonical rank.

## Migration Plan

Add one runtime migration that drops `runtime_turn_steering` and its unconsumed entries. Browser-only queued drafts are also discarded on upgrade. Messages already delivered and persisted in `session_history` remain. Stop old runtime replicas before that migration, because their startup guard and active request path still require the table. The Helm pre-upgrade migration path must scale the runtime down before applying it; installations using manual migration must perform the same sequence. Rollback requires restoring the old table/schema before starting old pods.
