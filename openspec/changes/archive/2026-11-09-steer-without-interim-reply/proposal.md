# Proposal

## Why

An in-progress update currently starts an extra model call solely to produce an assistant reply. That call delays the task, can fail or emit unsuitable content, and couples user-message delivery to assistant output. The agreed steer behavior is to redirect the ongoing turn and answer outstanding questions in its ordinary final response.

## What Changes

- Deliver each eligible update at the next safe model boundary, before the model continues, without generating an interim assistant message.
- Preserve durable message identity, definitive rank, pending clock, checkpoint recovery, and cross-replica idempotency.
- Direct the continuing model to account for updates in order and address outstanding questions in its final response.
- Remove interim reply generation, retry, fallback, storage, usage accounting, and UI stream handling. Keep previously persisted assistant messages readable as ordinary history.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `managed-conversations`: Active-turn updates alter the ongoing turn without requiring a separate assistant reply.

## Impact

Fred runtime steering middleware, event ranking and history persistence, ReAct/Deep stream handling, conversation specs and runtime contract, and targeted provider/runtime tests. No new API or database table is required.
