# Design

## Context

See proposal.md. The current middleware injects pending user messages before a model call, but waits for a separate assistant reply before delivering all but the opening message. History ranks and checkpoint identity already live in shared Postgres storage; the runtime has an existing steered-user event that can promote one message without an assistant row.

## Goals / Non-Goals

**Goals:**

- Make delivery a durable boundary operation that completes before normal model work.
- Preserve rank, UI clock, checkpoint recovery, and cross-replica behavior.
- Remove the special model request and all reply-specific state and rendering.

**Non-Goals:**

- Provide an immediate answer to a progress question.
- Change Graph's next-turn fallback or delete previously stored assistant replies.

## Decisions

### Deliver user events independently

The middleware gathers pending updates in provisional-rank order and emits one existing steered-user runtime event per update. The event ranker reserves a canonical rank and promotes the row under the conversation lock. A persistence receipt blocks the normal model call until delivery succeeds. This retains the established event/rank path while removing the assistant row and its transaction. A failed receipt prevents model work from proceeding with a message that still appears pending.

The browser submits steer requests for one session in send order, including their execution preparation. Optimistic messages appear immediately. This keeps database ranks aligned with the user's send order even when one preparation is slow. A definite rejection releases the next one. If the first POST outcome is uncertain, later submissions are refused until its identity is retried or delivered, because the server may still commit it. Different sessions remain independent.

The runtime persists the first managed turn's opening user message during admission, before returning the stream. The normal history writer later updates that same rank and exchange. This gives the session a durable agent instance identity before a first-turn steer is possible. Submission checks that identity, and the middleware reads pending updates only for its own instance. Direct-template turns cannot claim a managed update. No separate session binding or steering table is needed.
If the response closes before its generator starts, admission releases that opening row. An `execution_interrupted` result also releases it because the draft returns to the composer without creating a turn.
If an update was accepted before either cleanup, its pending row remains the session's instance identity for an idempotent submission retry and the next eligible turn.
Managed execution cannot adopt a session containing only direct-template history: it has no managed owner to bind to during admission. A new managed session ID is required.

### Recover from shared history

The graph checkpoints the middleware's injected user messages before entering the model-call wrapper. Managed ReAct and Deep execution requests synchronous LangGraph checkpoint durability so that write has committed before the wrapper runs. Promotion happens inside the wrapper. If promotion fails, the row remains pending; the next model boundary retries delivery and the stable message ID prevents duplicate injection. If the runtime stops after promotion, the checkpoint already carries the user message. Promotion rejects a stale read from another exchange while a retry in the owning exchange remains idempotent. The middleware keeps no process-local queue or reply identity. Existing historical assistant replies remain in stored history but are not created or replayed as a special steering step.

If the active turn ends before delivery, the oldest pending update opens the next ordinary turn. The frontend applies this rule to all send paths, including commands and skills; the runtime returns HTTP 409 for API callers that try to overtake it. Human-input resumes and Graph interruption recovery are exempt because they continue or restart the interrupted work. The pending update remains for the next ordinary turn. An opening pending identity cannot accompany a resume or a Graph interruption action. This prevents an older pending instruction from being appended after a newer ordinary input in model context, or being marked delivered without reaching the model.

### Use the ordinary model decision

The continuing model receives ordered user updates with guidance to apply revisions and answer remaining questions in its final response. It retains its ordinary tools and reasoning configuration. Remove the temporary no-tools request, two-attempt validation, fallback text, special continuation prompt, and Mistral-only output controls added for that request.

## Risks / Trade-offs

- A status question may wait until the final answer. The clock indicates delivery, and the existing tool trace shows ongoing activity.
- Synchronous checkpoint persistence adds a database wait per managed ReAct/Deep graph step. That wait is necessary before promoting a user message; non-managed runs retain the existing asynchronous mode.
- A failed history write leaves the clock visible and stops the model call; a later boundary retries against the checkpointed message.
- Several updates arriving during a boundary can straddle it. Only updates observed before that boundary are delivered; later ones remain pending for the next eligible boundary or turn.

## Migration Plan

No schema change. Existing reply rows remain part of historical conversations. The change ships in the current draft PR before the new steering contract is merged; existing local sessions should be checked for replay compatibility. Rollback restores the prior runtime behavior without rewriting history.
