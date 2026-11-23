## Context

The tab already owns running turns in `backgroundTurns.ts`. Queue state currently belongs to `useManagedChat` and is cleared on session changes. The agreed scope retains browser memory only.

## Goals / Non-Goals

Goals: preserve per-session FIFO and delivery status across navigation, including a turn completing in the background; never send queued turns before the conversation is reopened.

Non-goals: background queue execution, reload recovery, SQL/API changes and automatic SSE reconnection.

## Decisions

Use the existing registry as the queue owner and subscribe the visible hook to its current session. Remove delivered steering IDs even when detached. Clear only the owning turn's queue on real interruption, Stop or deletion. Keep empty queues out of the registry; consume entries through the existing visible FIFO path. Preserve HITL and uncertain-delivery rules. A session change resets view-local drain ownership, not retained text.

The user approved this scope before implementation. State is tab-local and does not coordinate backend replicas; existing SQL steering ownership and cleanup remain authoritative there.

## Risks / Trade-offs

Late events must not delete a replacement turn's queue or touch another session. Reattachment must block drain immediately, before React commits its streaming state. Queue entries retain memory until consumed, removed, discarded or the tab closes; no extra persistence or aggressive expiry is introduced.
