# Proposal

## Why

In a ReAct conversation, a few large tool results can push completed work past the model-input character budget. The current tail trim can then discard both the user's task and the assistant's continuation plan, so a short follow-up such as "continue" is answered without its context. This occurred in a CSV-to-workbook conversation on 2026-11-26. Tracking issue: #3704, under Epic #2833.

## What Changes

- Preserve leading system context and the user and final assistant messages of completed turns when ReAct must shrink model input. Remove completed tool rounds from that model input before dropping conversational context.
- Use a pure budgeted compaction helper whose size measurement is supplied by the caller, so a later token-based budget can use the same selection policy.
- Preserve the active user request and latest complete tool round. Remove older complete tool rounds within the active turn when necessary, and fail explicitly if the protected context cannot fit.
- Keep persisted checkpoints, visible history, Deep's native context handling, and Graph behavior unchanged.

## Capabilities

### New Capabilities

- `agent-context-management`: safe selection of ReAct conversation context under a model-input budget.

### Modified Capabilities

None.

## Impact

- ReAct model-input hygiene and its pure message helpers in `libs/fred-runtime`.
- Focused runtime tests and the compact runtime execution contract.
- No public API, database migration, dependency, or frontend change.
