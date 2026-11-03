---
schema: 1
title: "Preserve chat queues and clarify background conversation status"
impact: none
no_action_reason: "Only browser-tab queue ownership and local sidebar indicators change; deployment, runtime and database contracts are unchanged."
configuration: none
configuration_reason: "The existing background-turn registry holds the per-session queue; sidebar indicators use best-effort tab-local sessionStorage without new settings."
---
## Applicability

Managed chats using background generations from the in-app navigation change.

## Prerequisites

Deploy together with or after the background-generation frontend change.

## Configuration

No configuration changes are required.

## Upgrade

Deploy the frontend normally. No database migration, runtime upgrade procedure or data backfill is required.

## Validation

Queue text, navigate elsewhere while generation continues, then return before or after it finishes. The queue is retained and ordinary sends resume only in the open conversation after generation, history and human-input holds resolve. Delivered steering is removed even while detached. Stop, deletion and genuine stream interruption discard only the matching queue.

A conversation waiting for user input displays a localized chip. Known waiting and unread indicators survive refresh in the same tab; the existing history load reconciles waiting. A normally completed background answer displays a plain blue unread dot; errors and interrupted streams do not signal an answer ready.

## Rollback

Restore the previous frontend normally. Queued text is browser memory only; tab-local indicator data is ignored by the previous frontend.

## Limitations

Reload or tab close loses the queue. Ordinary queued turns do not execute in the background. Indicators are best-effort, bounded to 100 ids per type, and not shared between tabs/devices; storage failures fall back to memory.
