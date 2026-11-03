---
schema: 1
title: "Preserve pending chat messages across in-app navigation"
impact: none
no_action_reason: "Only browser-tab queue ownership changes; deployment, runtime and database contracts are unchanged."
configuration: none
configuration_reason: "The existing background-turn registry holds the per-session queue without new settings or persistence."
---
## Applicability

Managed chats using background generations from the in-app navigation change.

## Prerequisites

Deploy together with or after the background-generation frontend change.

## Configuration

No configuration changes are required.

## Upgrade

Deploy the frontend normally. No Alembic migration, runtime upgrade procedure or data backfill is required.

## Validation

Queue text, navigate elsewhere while generation continues, then return before or after it finishes. The queue is retained and ordinary sends resume only in the open conversation after generation, history and human-input holds resolve. Delivered steering is removed even while detached. Stop, deletion and genuine stream interruption discard only the matching queue.

## Rollback

Restore the previous frontend normally. Queued text is browser memory only.

## Limitations

Reload or tab close loses the queue. Ordinary queued turns do not execute in the background.
