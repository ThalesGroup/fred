## Why

The first submission can create a conversation but leave its draft unsent. A render before the router binds the new session clears the local-creation exemption introduced by PR #2993, so the availability guard aborts the turn.

## What Changes

- Retain local creation ownership across intermediate renders during the first route handoff.
- Keep saved, unresolved or deleted-agent conversations protected, including navigation away and back.
- Cover the handoff with a controlled deferred-navigation regression.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `managed-conversations`: make first-turn compatibility explicit across asynchronous router binding.

## Impact

Frontend managed-chat state and regression tests only. No backend contract, permissions, schema or configuration changes. Scope approved in the conversation on 2026-10-12; origin: #2992 / PR #2993.
