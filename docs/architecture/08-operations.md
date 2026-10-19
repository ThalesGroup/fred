# 8. Operations

## Configuration, secrets and identity provisioning

The Fred chart holds application defaults. Instance values select service addresses
and reference existing Secrets. The manager configuration schema is generated from
its Rust configuration types and embedded in the chart schema. API and worker mount
the same manager configuration and lifecycle catalog; changes to either input roll
both processes. Credentials remain environment references: the API receives its
identity client and bootstrap secrets, while the worker needs SQL and OpenFGA access.

## Deployment topology and environments

The default Fred release deploys manager API/worker, Knowledge Flow API/worker and
frontend, using three images. Each API/worker pair uses the same image. The Knowledge
Flow worker serves all configured ingestion roles in this composition. The legacy
control-plane and agent runtime are disabled. Existing frontend pages and routes
remain present; calls to absent services fail at request time without preventing
frontend startup.

On local k3d, the factory builds the Fred checkout, imports images, reconciles
identities and synchronizes the single `fred-app` release. Its published legacy
release uses its pinned composition. A recognized standalone manager release is
retired only after validating ownership, stateless inventory and continuity of
live data/identity/lifecycle configuration and credential sources. Protected
manifest/values snapshots precede removal. Foreground removal waits for old
producers to stop before the Fred sync. There is an interruption between releases;
application rollout is not atomic. A failed sync is recovered by retrying the same
checkout and factory command, retaining infrastructure and data.

## Background work and scheduling

`fred-manager worker` runs the manager-owned Temporal lifecycle schedule on its
own queue. SQL receipts are the durable work source; acceptance has no Temporal
RPC. The worker polls due operations, applies bounded cleanup activities and
retains incomplete work for later sweeps. HTTP startup does not connect to Temporal.
[Manager operations](A3-manager-operations.md#space-deletion-lifecycle) defines
configuration, activation, progress and recovery.

## Logs, audit, metrics and diagnostics

## Migration, backup and recovery

On a dedicated local k3d, the factory's `make k3d-app-reset DIR=<fred checkout>`
previews a Fred data reset; `CONFIRM=reset` executes it. The product-owned
[reset hook](../../deploy/k3d/reset_data.py) retains Keycloak accounts, credentials,
installed images and infrastructure. It clears Fred data and authorization together,
including manager consent and bootstrap state, and removes pending Temporal work.
The same account therefore repeats CGU acceptance and platform bootstrap; importing
the bundle recreates spaces and grants while reusing existing Keycloak identities.

The hook recognizes the integrated five-process release and the previous split
composition. It refuses other applications and unsupported storage configurations. It
stops producers before deletion, replays installed SQL migrations and waits for
service readiness before reporting success. A partial failure leaves Fred stopped
and retains original replica counts for retry; it provides no data rollback.
This local reset is separate from production backup and recovery procedures.

## Implementation references

[Manager configuration, security audit and deployment](A3-manager-operations.md).
