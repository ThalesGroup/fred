## Context

The PR base already has a local queue and a SQL mailbox for cross-replica steering. Its added durable queue is unnecessary under the confirmed visit-scoped policy. See proposal.md for the final scope.

## Decisions

1. Restore local array ownership and existing ordinary queue actions. Remove GET/PUT pending routes, queue execution identity, history acknowledgement, API adapters and store registration. Queue clearing also invalidates the active local drain so late callbacks cannot restore messages or affect another visit.
2. Keep the existing temporary SQL pending/seen format, turn identity and HITL resume behavior. Protect the finalizer with `complete_cleanup`; always stop/join the heartbeat. An interrupted stream cannot retain a human-input offer. A normal pause retains existing steering semantics.
3. Reclaim expired rows in existing indexed batches of 256 with row locks every 60 seconds. An expired heartbeat cannot renew ownership. No migration or new retention state is needed.

## Risks / Trade-offs

Queued text and unfinished generation are intentionally visit-scoped. This change adds no background continuation or reconnect recovery. Existing row locks and turn identities provide multi-pod coordination; browser state is only the local view, not a shared execution lock. Test cancellation, navigation, late promises, normal HITL and PostgreSQL sweep/renew races.

## Migration Plan

Normal rollout and rollback; the existing table and JSON format are unchanged. The operator note declares impact none. Historical archived planning records the earlier proposal; current specs and the PR describe the simplified behavior.
