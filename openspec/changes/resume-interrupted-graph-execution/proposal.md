## Why

Refs #2892; PR #2903 delivers a bounded Graph slice and does not close the issue.
Marc's fred-rags workflow needs to publish the same prepared plan after an
interruption without regenerating it. The developer confirmed that the destination
supports safe replay. Fred should preserve that preparation and offer an explicit
continuation, without claiming to diagnose process death or solve distributed ownership.

## What Changes

- Persist Graph step state before starting the next step; keep completed preparation
  and persisted task results available when continuing.
- Treat pending non-HITL work as an unfinished execution, not proof of a dead process.
  Retain its checkpoint after a node error, step limit, cancellation or disconnect;
  report known errors without automatically erasing the continuation point.
- Offer an authorized user Continue, Restart or Later. Continue reuses saved state;
  Restart starts a new turn and does not undo an external effect; Later runs nothing.
- Keep the existing event/request names and generated client. Continue accepts no new
  input. Refused HTTP requests retain the recovery controls and Stop intent.
- Retain existing continuation admission as a bounded guard and close the underlying
  stream before releasing it. Support one active execution per Graph conversation;
  concurrent new turns/Restart and distributed failover coordination remain unsupported.
- Validate prepare/publish/finalize with a domain-neutral idempotent destination;
  the author owns operation identity, content and reconciliation, not the runtime.
- **BREAKING:** clients reusing an unfinished Graph conversation must handle the
  continuation event instead of expecting an automatic new turn. Node failures can
  now leave unfinished work; older clients need the paired frontend/runtime release.

## Capabilities

### New Capabilities

- `interrupted-graph-execution`: preserve prepared Graph work and explicitly continue
  it under a single-active-execution usage contract.

### Modified Capabilities

None.

## Impact

SDK request validation, Graph executor lifecycle, runtime history, generated client,
chat recovery controls, tests and existing contract/UX/migration documents. No new
schema, dependency, lease, heartbeat, external-operation journal or generic retry
mechanism. ReAct, Deep and ordinary HITL are unchanged.

This revision narrows the existing change, rather than introducing a parallel one.
The current implementation still follows parts of the previous design; tasks.md
records the remaining delta. Earlier verification.md results are historical evidence,
not acceptance of this revised contract.
