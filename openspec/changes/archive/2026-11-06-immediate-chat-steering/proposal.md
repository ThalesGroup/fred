## Why

An active managed turn currently puts additional user text in a browser-only queue and requires a second action to steer the agent. This delays feedback, loses unsent messages on reload, and makes conversation order depend on a separate mailbox rather than the chat history.

## What Changes

- Submit plain text directly into the conversation during an active ReAct or Deep turn. Show it immediately with a subtle pending indicator that disappears when the model incorporates it.
- Persist each submitted message in conversation history at a fixed provisional rank. Keep it visually at the end while pending, then assign its definitive rank once at the safe model boundary. Continue ordering canonical history by rank.
- Deliver after the current tool-call/result batch, preserve the message across pod changes and restarts, and run it as the next ordinary turn if the current turn ends first. Hold it through a human-input pause.
- Send a separate assistant reply to an in-progress update before resuming normal work, including a direct status answer when the user asks for progress.
- Remove the browser queue, its disclosure and actions, the steering mailbox table, and its cleanup path. Drop unconsumed mailbox entries during the same migration; already persisted conversation messages remain intact.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `managed-conversations`: Replace queued steering with durable in-thread submission, explicit receipt state, rank reconciliation, and recovery behavior.

## Impact

Managed chat UI and SSE handling, runtime turn middleware and HTTP API, shared history store/schema, runtime Alembic migration, deployment migration sequencing, and conversation UX/runtime documentation.
