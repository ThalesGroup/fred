## Why

People cannot draft or submit another message while an agent is working. They also cannot steer a long tool-using turn at its next decision point.

## What Changes

- Keep the managed chat composer available during an active turn and show a small ordered pending-message list above it.
- Let a person edit or remove a pending message, wait for the turn to finish, or request delivery at the next safe model boundary.
- Add an authenticated runtime steering request for active ReAct and Deep turns, plus a stream event when a message is actually consumed.
- Fall back to the next ordinary turn if the active run reaches no further safe boundary. This first prototype uses process-local steering state; it is intended for local evaluation, not multi-replica deployment.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `managed-conversations`: pending and mid-turn managed chat message behavior.

## Impact

Managed chat UI, its SSE transport, the runtime execution endpoint and ReAct/Deep middleware, runtime event/history contracts, and focused tests. Graph agents retain their existing execution behavior in this prototype.
