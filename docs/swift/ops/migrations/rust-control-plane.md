---
schema: 1
title: "Replace the Python control-plane with the Rust control-plane"
impact: major
configuration: production
configuration_reason: "The control-plane-backend image and workloads run Rust control-plane with its own configuration; optional storage.content enables S3 original storage."
---

## Applicability

Fred deployments adopting the Rust control-plane reconstruction. Manager serves
organizations, teams, projects, personal spaces, roles, provisioning, folders,
immutable originals, worker-driven document processing and deferred space deletion. The local profile runs `control-plane-backend` with its background tasks in one process,
next to Knowledge Flow worker and the frontend. The
Python control-plane and fred-agents do not run. APIs not yet reconstructed fail.

## Prerequisites

Fred does not migrate existing data. Users, roles, teams, conversations and
documents from a Python control-plane or Knowledge Flow installation are the
concern of a separate migration application, never of Fred code.

SQL schema evolution uses numbered, immutable SQLx migrations. The migration Job
applies them; API startup checks versions and checksums. OpenFGA model compatibility
is checked independently. Persisted identifiers renamed by this reconstruction
are not automatically migrated. Use a fresh disposable secondary installation
for the new identifiers, or prepare an explicit data migration before upgrading
an installation whose data must be retained. The Rust ingestion profile does not
support `k3d-app-reset`; no reset command should be used as a schema migration.

## Configuration

Configure manager on `applications.control-plane-backend`; API and worker share its
configuration and lifecycle catalog. `security.m2m.enabled` is required; the chart
default sets it to `true`. The existing `control-plane` Keycloak client
and `fred-secrets/KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET` supply directory access;
`CONTROL_PLANE_BOOTSTRAP_TOKEN` remains the bootstrap secret. Manager uses database
`fred`, OpenFGA store `control-plane` and lifecycle queue `control-plane-lifecycle`.
Space deletion stays disabled until `scheduler.lifecycle.enabled` is set.

Original storage is optional and disabled when `storage.content` is omitted. To
enable it, adapt the configuration fragment
`deploy/charts/fred/examples/document-storage.yaml`, preserving existing environment
lists. The private Swift documents bucket has no versioning, Object Lock or enabled
lifecycle rules. Grant input writes, input/output reads, inventory and bucket
configuration reads. The complete factory profile and commands are in
[deploy/k3d](../../../../deploy/k3d/README.md).

## Upgrade

Use the [checkout-owned local profile](../../../../deploy/k3d/README.md) with
`make k3d-app ENV=secondary APP=fred DIR=../fred` from the deployment factory.
The migration hook applies the embedded SQLx migration chain with `DATABASE_URL`
only. This command does not rename existing databases, stores, queues or indexes.

## Validation

Check the three application Deployments: control-plane-backend, knowledge-flow-worker
and frontend. Log in,
accept the active CGU, bootstrap the platform owner and import a provisioning ZIP.
An editor creates a folder in Resources; with original storage enabled, uploads a
file, reloads and downloads identical bytes. An admin alone cannot read content.

## Rollback

There is no data rollback. Returning to the Python control-plane requires restoring
coordinated SQL, OpenFGA and object storage backups taken before the switch, with
manager writers stopped.

## Limitations

Manager does not serve agents, conversations or retrieval search, and does not
evaluate Python platform-access admission or the team-administrator charter.
Individual originals are capped at 100 MiB; processing has its own persisted result.

## Optional document processing

Apply `deploy/charts/fred/examples/document-processing.yaml` after the storage and
instance values. Replace example addresses and merge existing environment/volume
lists (Helm replaces lists). Manager and every KF worker role use the same Temporal
host, namespace and base queue. Namespace history retention must exceed
`scheduler.processing.limits.queue_seconds`; otherwise delivery is refused.

Use the same endpoint, bucket and prefix for originals and derived artifacts.
Restrict worker credentials to output paths, including listing; KF obtains
originals through manager. The [canonical layout](../../../architecture/A9-documents.md#physical-object-layout)
preserves Swift names and adds only immutable processing generations below output.
Disable legacy PDF expiry and keep legacy corpus mutation credentials away from
manager documents. GCS/S3NS enforcement must be validated with the actual API and
identity mode; the local SeaweedFS fixture does not prove that contract. Configure
`manager_processing.vector_store` with a distinct durable collection, index or
table, separate from legacy KF because its readers do not enforce manager
publication/ReBAC. The chunk mapping stays unchanged; generation-scoped IDs prevent
stale writes. Original quota is charged once; derived capacity
and worker temporary storage have independent limits. Size each extraction pod's
ephemeral storage for its activity concurrency. The existing worker image supplies
LibreOffice for Word, ODT and PowerPoint native PDF previews.

Provision the confidential service-account client described in
`deploy/charts/fred/examples/manager-worker-client.json` in the application realm.
Store its generated secret in the instance Secret referenced by
`MANAGER_WORKER_CLIENT_SECRET`. Tokens must carry the configured issuer, manager
audience, client_id and service-account username. Manager checks all four independently
of browser authentication. Rotate the Secret and restart KF workers. Human tokens
cannot call worker persistence endpoints.

Export from the deployed KF worker configuration:

```sh
cd apps/knowledge-flow-backend
.venv/bin/python -m knowledge_flow_backend.features.scheduler.export_contract --configuration /path/to/worker.yaml > /tmp/worker-contract.json
kubectl create configmap manager-processing-contract --from-file=worker-contract.json=/tmp/worker-contract.json --dry-run=client -o yaml
```

Apply that manifest in the release namespace through the normal deployment path.
The credential-free export contains the existing `PipelineDefinition` schema,
three resolved submission policies and processor profile settings. Mount it as
shown in the overlay. Export again when changing KF policy, then roll manager.
Accepted attempts retain their policy; the export does not pin deployed Python
code. Drain before incompatible worker or queue changes.

Enable manager `scheduler.processing.enabled` and KF `manager_processing.enabled`.
Disabling manager admission preserves upload-only, original download and published
previews; its worker continues delivery, reconciliation and expiry of accepted
attempts. Keep configuration, credentials and KF workers until attempts are terminal
and abandoned outputs are cleaned. Removing worker support is not a drain operation.

Validate with KF HTTP stopped: upload with processing into Resources, reload,
inspect File/Raw previews and download identical original bytes. Retry a failure
without selecting the file again. Manager outputs stay isolated from legacy KF
search and chat retrieval. Failure never deletes the original.

The disposable real-worker check requires Docker, the KF Python environment and
LibreOffice on PATH:

```sh
CONTROL_PLANE_IT_PROCESSING=1 INTEGRATION_POSTGRES_IMAGE=pgvector/pgvector:pg15 make -C apps/control-plane test-integration CARGO_TEST_OPTS=processing_existing_worker_journey
```

It uses real Temporal, object storage and vector persistence with local model and
identity protocol fixtures. It starts no KF HTTP server and resets no existing
installation. Ordinary integration runs omit this optional heavy journey.
