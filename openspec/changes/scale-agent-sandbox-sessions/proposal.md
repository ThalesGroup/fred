## Why

The current broker keeps admission and conversation leases in one process. A second replica would admit beyond the intended ceiling, while idle pods occupy capacity for the full conversation timeout. The 1,000-request k3d check confirmed clean overload handling at a 12-sandbox cap, but not production-scale execution.

## What Changes

- Coordinate conversation ownership, execution serialization and active capacity across broker replicas using Fred's PostgreSQL deployment, with bounded waiting and per-tenant queue limits. Keep the current in-process mode for local Docker development.
- Separate the active-pod idle period from the 20-minute conversation expiry. Suspend idle Kubernetes sandboxes and resume them with private `/work` content intact; delete the workspace at final expiry. Preserve read-only, live `/inputs` and `/skills` mounts.
- Permit the Fred chart to run multiple broker replicas only with the shared coordinator and a persistent workspace profile. Add operator-controlled sandbox node placement, explicit RuntimeClass overhead guidance and capacity metrics. Keep zero preloaded sandboxes and the approved Kata/gVisor choice.
- Bound sandbox creation and Kubernetes API pressure under bursts. Measure cold/resume latency and capacity with the full mount profile before recommending production limits.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-code-sandbox`: Shared admission, bounded waiting, suspend/resume lifecycle, persistent conversation scratch and multi-replica recovery.

## Impact

- Broker session coordination, backend lifecycle and API; a dedicated PostgreSQL session table and migration; Fred chart and deployment guide; focused concurrent and lifecycle tests.
- The scalable profile requires PostgreSQL and an approved persistent workspace StorageClass. Local Docker retains the existing single-broker behavior unless explicitly configured for persistent workspaces.
- No new model-visible tool arguments, arbitrary admin runtime settings, cross-user sandbox reuse or warm pod pool.

Tracking issue: ThalesGroup/fred#3286. This change is stacked on the agent sandbox PR.
