## Context

The runtime stores a complete turn's trace after the SSE stream, while the steering mailbox stores unconsumed text separately. `session_history` already has a per-session rank key and is the authoritative history read path. The browser groups adjacent tool calls/results into trace segments and starts a new visual segment at each user row. A pending user row therefore must be rendered outside canonical trace order until a model boundary is reached.

## Goals / Non-Goals

**Goals:** Keep one durable user-message identity across HTTP retries, SSE delivery, history reload, and a later ordinary turn. Assign one fixed provisional rank at receipt, and one definitive rank at incorporation. Preserve rank ordering of canonical trace and checkpoint recovery across runtime replicas.

**Non-Goals:** Steering an already running Graph turn, queuing attachments or commands, and canceling an in-flight tool call. The model cannot undo a tool call dispatched before the new message was sent.

## Decisions

### Store message state in `session_history`

Use a user/final row with nullable `message_id` and `delivery_state` columns, exposing these through `metadata.extras` on history reads. A unique `(session_id, user_id, message_id)` index and a `(session_id, user_id, delivery_state, rank)` index make retries and pending scans bounded. The provisional rank is a negative per-session sequence allocated in a transaction; canonical ranks remain nonnegative and increasing. A pending row has its own temporary `exchange_id`, replaced by the actual exchange at delivery, so legacy exchanges with empty IDs cannot absorb it. The browser orders only pending rows at the visible end by their provisional sequence. This reuses the existing history lifecycle and ownership model. A new queue table would recreate the current dual-source failure mode.

### Reserve canonical rank from the turn's trace sequence

At turn start, wait for the preceding turn's history commit and capture `MAX(canonical rank)+1`. A single rank allocator reserves positions for both SSE events and persisted trace rows. The stream sends these ranks with each ranked event, so the live browser and reloaded history use the same order. At the safe model boundary, a `steered_user_message` event atomically moves its pending row to its canonical rank and marks it delivered, before new model output can reserve tool ranks. The turn writer persists the other events at their reserved ranks, skipping a second user row for that identity. Synthetic `tool_use` thoughts do not consume a canonical rank. Rank gaps from empty reasoning blocks remain allowed. A later pending message keeps its negative rank until its own boundary.

### Make the history write part of stream completion

Finish writing the collected trace before the SSE stream closes, instead of spawning the write after close. This makes the next turn's initial rank reliable and removes a race with a follow-up submission. The final SSE frame still arrives promptly; the close waits for persistence. The endpoint also writes history on an interrupted stream, preserving already visible trace where possible.

### Treat the model boundary as delivery, and reconcile checkpoints

The middleware reads pending rows in send order from shared SQL, injects stable LangGraph `HumanMessage.id` values after the completed tool batch, and emits one delivery event per incorporated message. On continuation, it compares every delivered identity from the current exchange with checkpoint messages before re-injecting, even if the trace was persisted before the checkpoint. Delivery state is durable only after the rank move succeeds. A crash between an external model call and checkpoint commit can replay that call, as with other runtime work; the stable message identity prevents a second history row and a later checkpoint comparison avoids duplicate context injection.

### Continue a message that misses the boundary

After a completed turn with pending rows and no human-input hold, the open chat starts one ordinary turn using the oldest persisted pending message identity. The runtime reserves that exchange's opening canonical rank for the row and promotes it at the first model boundary. The opening ReAct/Deep checkpoint message carries the same stable ID, so a later HITL resume cannot inject it again. Graph execution has no such boundary hook, so a Graph fallback acknowledges the row at its first final answer or human-input pause. If the browser closes, opening the conversation restores this state from history and continues it. During a human-input pause before an ordinary fallback starts, the message remains pending until the matching continuation reaches a boundary.

### UI state follows the persisted row

The composer creates an optimistic in-thread message keyed by a UUID, calls the authenticated runtime endpoint, and reconciles its rank and state from the response. A small clock is shown for `pending`. Delivery changes it to a check for roughly 1.5 seconds, then removes the icon. History reload uses the durable state; no browser pending queue or queue disclosure remains. If the next-turn attempt fails, the clock becomes a retry control while the chat is idle. Retrying keeps the same message identity. A network uncertainty resolves by refetching the same message ID, not by creating another identity.

## Risks / Trade-offs

- [History persistence adds latency at stream close] -> Keep one batched write, measure the additional close time, and avoid a database call per trace token.
- [Pending rows may be received while a turn is finishing] -> Serialize promotion and trace persistence per session; a late row remains pending for the following ordinary turn.
- [Model call and SQL/checkpoint commits are not one transaction] -> Use stable IDs and reconcile pending state with checkpoint messages on continuation. External tool/model effects remain subject to the runtime's existing retry semantics.
- [Negative provisional ranks are not canonical order] -> Only rows explicitly marked pending use the bottom-of-thread presentation rule. All delivered and ordinary messages continue to sort by canonical rank.

## Migration Plan

Add one runtime migration that drops `runtime_turn_steering` and its unconsumed entries. Browser-only queued drafts are also discarded on upgrade. Messages already delivered and persisted in `session_history` remain. Stop old runtime replicas before that migration, because their startup guard and active request path still require the table. The Helm pre-upgrade migration path must scale the runtime down before applying it; installations using manual migration must perform the same sequence. Rollback requires restoring the old table/schema before starting old pods.
