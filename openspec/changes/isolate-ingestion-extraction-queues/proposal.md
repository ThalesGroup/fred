## Why
Heavy PDF extraction must not starve fast/medium ingestion or common operations.

## What Changes
Isolate extraction into three profile queues; retain common orchestration and indexing.
Bound admission per profile, supervise extraction cancellation, and expose stage performance.
See [ingestion architecture](../../../docs/swift/design/INGESTION.md).

## Capabilities
### New Capabilities
- `ingestion-extraction-routing`: profile isolation and document execution guarantees.
### Modified Capabilities
None.

## Impact
Knowledge Flow scheduler, worker configuration and Helm deployments. No new UI/API surface.
**BREAKING:** drain ingestion before rollout; old in-flight histories are not supported.
