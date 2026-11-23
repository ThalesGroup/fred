## Why

A disconnected chat can leave an active steering row behind. The user confirmed that the queue must share the current chat visit's lifetime and explicitly requested removing unnecessary durable recovery machinery from PR #3399 (#3396).

## What Changes

- Keep ordinary pending messages in browser state; clear them on navigation, reload or SSE interruption without restoration.
- Remove the added durable-queue routes, SDK field, generated hooks and history acknowledgements.
- Keep cancellation-protected teardown, heartbeat shutdown, identity-safe steering cleanup and bounded expiry sweeps every minute.
- Keep text-only Renvoyer/Supprimer for other uncertain outcomes. No offered-message editing feature.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `managed-conversations`: define the local queue lifetime and temporary steering cleanup, superseding this PR's earlier recovery proposal.

## Impact

Existing chat hooks, steering mailbox/finalizer, focused tests and compact guidance. Reuse the existing SQL table and columns. No Alembic migration, new service, configuration or recovery protocol.
