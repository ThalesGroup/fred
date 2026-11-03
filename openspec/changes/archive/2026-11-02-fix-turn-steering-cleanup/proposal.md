## Why

Disconnecting a managed chat stream can leave its steering row active, while navigating away loses the ordinary browser-only message queue. Cleaning up abandoned execution state must not delete undelivered user messages. Tracking: [#3396](https://github.com/ThalesGroup/fred/issues/3396), following #3284.

## What Changes

- Make the existing SQL mailbox the authoritative, bounded queue for ordinary queued messages and immediate steering; restore it after navigation and reload.
- Separate turn lease expiration from message retention. Finalization and periodic cleanup release abandoned execution state without deleting queued or uncertain messages.
- Retain messages with uncertain delivery and require explicit retry; remove delivered entries only after durable history persistence.
- Complete cancellation-safe teardown and run the existing sweep every 60 seconds, deleting only expired empty rows.
- Reuse existing queue controls, statuses, identity checks, storage and connection pools; remove redundant browser-only ownership logic.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `managed-conversations`: Durable pending messages, conservative delivery recovery, and cancellation-safe reclamation of empty steering rows.

## Impact

- Runtime mailbox, queue routes and stream/history integration; SDK execution request identity for an ordinary queued message; generated runtime OpenAPI/client.
- Frontend queue loading, mutations and recovery in the existing managed chat hooks and controls, with focused backend/frontend tests.
- Runtime contract, queue UX guidance, and a migration note documenting coordinated runtime rollout and rollback limitations.
- Reuse `runtime_turn_steering` and its JSON payload, with no new table, infrastructure, dependency or configuration. Active leases remain 90 seconds and paused turn ownership remains 30 days; message retention no longer follows those leases.
