# 8. Operations

## Configuration, secrets and identity provisioning

The Fred chart holds application defaults. Instance values select service addresses
and reference existing Secrets. The manager configuration schema is generated from
its Rust configuration types and embedded in the chart schema. API and worker mount
the same manager configuration and lifecycle catalog; changes to either input roll
both processes. Credentials remain environment references: the API receives its
identity client and bootstrap secrets, while the worker needs SQL and OpenFGA access.

## Deployment topology and environments

The default Fred release has five deployments: `control-plane-backend` and
`control-plane-worker` run the Rust manager, `knowledge-flow-backend` and
`knowledge-flow-worker` run Knowledge Flow, and `frontend` serves the existing UI.
Each API/worker pair shares its backend image. The Python control-plane and agent
runtime do not run. Existing UI requests for unimplemented APIs fail at request time.

The unchanged deployment factory builds the Fred checkout and synchronizes its
`fred-app` release. The chart retains the standard control-plane service name,
port and identity client. Existing manager state remains in database `fred`,
OpenFGA store `fred-manager` and lifecycle queue/prefix `fred-manager-lifecycle`.
The frontend keeps the public `/fred-manager/v1` contract and forwards it to the
control-plane API. The factory's common Temporal host/namespace configure lifecycle
work; the lifecycle queue and workflow prefix remain manager-owned.

A pre-install/pre-upgrade hook applies the embedded baseline SQL schema using only the
database connection. API startup also verifies/applies it, and refuses a schema or
OpenFGA model that differs from the binary's. An upgrade
replaces the former manager-named workloads within the same Fred release. The chart
refuses a separately owned manager deployment; retiring that release is an explicit
operator action. Application rollout is not atomic. A failed sync is retried with
the same checkout and command, retaining infrastructure, credentials and data.

## Background work and scheduling

`fred-manager worker` runs the manager-owned Temporal lifecycle schedule on its
own queue. SQL receipts are the durable work source; acceptance has no Temporal
RPC. The worker polls due operations, applies bounded cleanup activities and
retains incomplete work for later sweeps. HTTP startup does not connect to Temporal.
[Manager operations](A3-manager-operations.md#space-deletion-lifecycle) defines
configuration, activation, progress and recovery.

Original-storage cleanup runs inside API processes, using SQL leases and bounded
S3 inventory pages. It has no Temporal dependency. Optional `storage.content`
configuration enables a dedicated bucket namespace and a bounded temporary volume
on the API only. The default deployment leaves content storage unconfigured;
folder browsing stays available. The [storage operations reference](A3-manager-operations.md#original-storage)
defines provider validation, limits, secrets and restore ordering.

## Logs, audit, metrics and diagnostics

## Migration, backup and recovery

Manager does not migrate Knowledge Flow documents; data from an existing Fred
installation is the concern of a separate migration application. SQL and the
matching object namespace form one
backup unit; restore suspends uploads and cleanup until both are consistent. The
[migration note](../swift/ops/migrations/rust-fred-manager.md) defines activation
and rollback constraints.

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
