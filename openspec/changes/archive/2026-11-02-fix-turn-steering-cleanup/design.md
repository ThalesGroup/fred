## Context

See proposal.md for motivation. `runtime_turn_steering` already stores one SQL row per session with bounded pending messages, turn ownership and an indexed expiration. The ordinary queue separately lives in React state and is cleared on navigation. `take()` clears pending entries before their delivery is durable, `start()` can reset them, and `end()`/expiration cleanup can delete the row. All four paths must change together.

## Goals / Non-Goals

**Goals:** Preserve accepted messages across navigation and pod failure with one authoritative queue; keep execution ownership and storage bounded; reuse existing code and UI.

**Non-Goals:** Background execution after leaving chat, automatic retry of uncertain delivery, an exactly-once execution guarantee, a new broker/scheduler, or a general-purpose queue framework.

## Decisions

1. Extend the existing SQL row and pending JSON entries with `waiting`, `offered` and `uncertain` statuses. Keep the existing 32-message bound and configured text limit. Reuse ownership columns, row locks and the async pool. Session metadata belongs to Control Plane and delivered history belongs to the runtime; neither is a natural home for another mutable queue. No new table or parallel browser persistence is needed.
2. Add a small runtime API to read and mutate individual queue entries. Reuse managed session ownership and execution authorization checks, stable message IDs, and generated API types/hooks. Mutate by message ID under the row lock rather than replacing the whole list, preventing stale tabs from overwriting each other. Repeated creation of an existing ID must not add another entry. Bound per-turn deduplication bookkeeping.
3. Persist enqueue before acknowledging it to the UI. Ordinary queued execution carries the queue message ID; the runtime atomically claims a waiting entry before dispatch. Immediate steering selects an existing entry for its matching active turn. Normal starts preserve pending entries; they never reset the queue. Competing tabs or replicas cannot claim the same entry twice.
4. Mark an entry `uncertain` before handing its content to execution and retain its text. An SSE delivery event may update the current view, but must not authorize durable deletion. Remove delivered entries only after their user-message history has been durably written; carry their IDs through the existing history path. A crash between dispatch and history persistence leaves an explicit uncertain entry, with no automatic retry. This conservative rule avoids adding checkpoint reconciliation or a distributed transaction protocol.
5. Finalization stops/joins the heartbeat and releases only its own turn inside `complete_cleanup()`. Return offered-but-unconsumed entries to waiting when ordinary execution ends; retain paused offers for the matching HITL resume. Preserve uncertain entries and replacement turn ownership. Expiration releases abandoned ownership, not message contents; an expired human pause must not erase pending messages.
6. Keep startup cleanup and change the existing periodic sweep to 60 seconds. Delete only expired rows with no pending/uncertain entries, atomically checking emptiness and expiration. Lock at most 256 expired rows using the expiration index and `SKIP LOCKED`. Park retained queues in idle state with no expiring lease so later sweeps do not rescan them; an empty idle queue becomes eligible for deletion again. Session erasure continues to purge its entire mailbox. No cleanup task may depend on its own replica owning the abandoned turn.
7. Replace the local-only queue lifecycle with a server-backed view in the existing managed chat hooks. Load once on conversation entry and refresh after queue operations and turn completion; no continuous polling. Guard late responses by session identity. Reuse edit/remove/Send/retry controls. Restoring a queue does not automatically start execution; Send explicitly resumes it. Maintain ordinary FIFO draining while the user remains in the active conversation.

## Risks / Trade-offs

- SQL outage: keep unsaved input visible and report the failed operation; do not claim that a message was queued. Existing request/connection timeouts apply.
- Delivery/history writes are not atomic: preserve uncertain text and require explicit retry. Do not claim exactly-once execution or infer durable delivery from an SSE event.
- Retained messages consume storage: bound queue count and text size, and reuse session erasure. Lease expiration is not a message-retention policy.
- Old replicas delete pending state: drain old runtime replicas before activating durable queue writes. Rollback with nonempty queues can lose pending entries and must be documented.
- More frequent sweeps: reuse the indexed expiration predicate and shared pool outside the hot path; verify competing sweep/renew/claim operations against real PostgreSQL.

## Migration Plan

Keep the existing table schema and interpret legacy `{id, text}` entries as offered messages for their recorded turn. Include pending JSON compatibility tests. Deploy runtime and frontend together after draining old runtime replicas; do not allow old cleanup code to operate on the durable queue. Record `impact: minor` for this rollout requirement, with validation and rollback guidance in the new migration note. No chart configuration changes are required.
