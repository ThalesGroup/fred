---
schema: 1
title: "Preserve queued chat messages across disconnects and navigation"
impact: minor
configuration: none
configuration_reason: "The existing runtime SQL mailbox and connection pool hold the durable queue; no configuration or chart fields change."
---
## Applicability

Fred deployments using managed chat queues and turn steering.

## Prerequisites

The existing `runtime_turn_steering` migration must already be applied. No new schema migration is required.

## Configuration

No new configuration. Queues hold at most 32 messages and apply the existing chat text limit.

## Upgrade

Drain old runtime replicas before activating the updated runtime and frontend. Older runtime code deletes mailbox contents at turn completion and expiry, so do not mix old and updated replicas after durable queue writes begin. Deploy the runtime before enabling the updated frontend. Existing legacy steering entries remain readable.

## Validation

Queue a plain-text message, leave the conversation, and reopen or reload it. The queued text must reappear without automatic execution. Click Send to resume. Disconnect an active turn and confirm pending or uncertain messages remain recoverable. Expired empty mailbox rows are reclaimed at startup and every minute, in batches of at most 256 rows.

## Rollback

Before restoring the older runtime, finish queued messages or explicitly remove them. Rolling back with nonempty queues can lose those messages because older cleanup does not preserve them. Restore the matching frontend with the runtime. No schema downgrade is needed.

## Limitations

A failure after dispatch but before history persistence leaves delivery uncertain. Check the conversation before explicitly retrying, as retry can duplicate work. Messages persist until durable delivery, explicit removal or conversation erasure; turn lease expiration does not delete them. Existing browser-only messages from before upgrade cannot be recovered after that browser state was lost.
