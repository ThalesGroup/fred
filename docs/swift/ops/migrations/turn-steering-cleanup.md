---
schema: 1
title: "Reclaim abandoned chat steering turns"
impact: none
no_action_reason: "Only application lifecycle cleanup changes; the existing mailbox schema and temporary JSON format remain unchanged."
configuration: none
configuration_reason: "The existing temporary steering table, lease index and async pool are reused; no schema or deployment settings change."
---
## Applicability

Managed chats using the existing `runtime_turn_steering` table.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy normally. No Alembic migration, data backfill, configuration change or special pod drain is required. The ordinary pending list stays local to the browser; no durable queue format is introduced.

## Validation

Queue text during generation, then navigate within the application and return: the queued text and active turn must remain. Interrupt the stream: the local list must disappear and stay empty on return. Normal completion and human-input pauses keep their existing queue behavior. Expired steering rows are reclaimed at startup and every minute, in batches of at most 256 rows; late cleanup must preserve a replacement turn.

## Rollback

Restore the previous frontend and runtime normally. No schema downgrade is needed.

## Limitations

Pending messages remain in browser memory across in-app navigation. They are not recoverable after a page reload, a stream interruption or explicit cancellation.
