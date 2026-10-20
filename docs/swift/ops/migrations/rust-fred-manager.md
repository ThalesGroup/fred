---
schema: 1
title: "Replace the Python control-plane with the Rust fred-manager"
impact: major
configuration: production
configuration_reason: "The control-plane-backend image and workloads run Rust fred-manager with its own configuration; optional storage.content enables S3 original storage."
---

## Applicability

Fred deployments adopting the Rust fred-manager reconstruction. Manager serves
organizations, teams, projects, personal spaces, roles, provisioning, folders,
immutable originals, worker-driven document processing and deferred space deletion. It runs as `control-plane-backend`
and `control-plane-worker`, next to Knowledge Flow API/worker and the frontend. The
Python control-plane and fred-agents do not run. APIs not yet reconstructed fail.

## Prerequisites

Fred does not migrate existing data. Users, roles, teams, conversations and
documents from a Python control-plane or Knowledge Flow installation are the
concern of a separate migration application, never of Fred code.

Manager keeps no backward compatibility before its first production release: its
SQL schema is one baseline and its OpenFGA model is replaced, not upgraded. Startup
refuses a database or store created by an earlier manager build. On a dedicated
factory k3d, preview with `K3D_RESET_FOR_UPGRADE=1 make k3d-app-reset
DIR=<target fred checkout>`, then execute with `CONFIRM=reset`. This leaves Fred
stopped and its SQL/OpenFGA state empty so the target images install their own
baseline and model. Deploy the target release next; do not restart the old images.
The ordinary reset without `K3D_RESET_FOR_UPGRADE=1` reinstalls the current release
and is only suitable for the same version. Keycloak accounts and infrastructure
are retained. The local reset accepts manager buckets `fred-manager-originals` and
`fred-manager-derived` only on the local SeaweedFS endpoint, manager vectors in
`fred-manager-vectors` on local OpenSearch, and processing in the local Temporal
`default` namespace. External or custom storage is refused before any deletion.

## Configuration

Configure manager on `applications.control-plane-backend`; API and worker share its
configuration and lifecycle catalog. `security.m2m.enabled` is required; the chart
default sets it to `true`. The existing `control-plane` Keycloak client
and `fred-secrets/KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET` supply directory access;
`CONTROL_PLANE_BOOTSTRAP_TOKEN` remains the bootstrap secret. Manager uses database
`fred`, OpenFGA store `fred-manager` and lifecycle queue `fred-manager-lifecycle`.
Space deletion stays disabled until `scheduler.lifecycle.enabled` is set.

Original storage is optional and disabled when `storage.content` is omitted. To
enable it, apply `deploy/charts/fred/examples/document-storage.yaml` as an instance
overlay with a private bucket that never has versioning, Object Lock or enabled
lifecycle rules, and grant Put/Get/Delete/List plus bucket configuration reads.

## Upgrade

From the unchanged factory `swift` checkout, run `make k3d-app APP=fred DIR=../fred`.
When the previous build used manager-named applications, first move the active
cache's `.cache/k3d-apps/fred-<id>/images.yaml` and `images.txt` aside; otherwise
the initial lint rejects the retired names. The migration hook applies the SQL
baseline with `DATABASE_URL` only. A separately owned `fred-manager` release is
refused: retire it explicitly before retrying.

## Validation

Check five ready application Deployments with matching API/worker images. Log in,
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

Provision a second private S3 bucket for derived artifacts with versioning,
Object Lock and lifecycle rules disabled. Restrict worker credentials to derived
data; KF needs no credentials for originals. Configure
`manager_processing.vector_store` with a distinct durable collection, index or
table, separate from legacy KF. Original quota is charged once; derived capacity
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
CONFIG_FILE=/path/to/worker.yaml .venv/bin/python -m knowledge_flow_backend.features.scheduler.export_contract > /tmp/worker-contract.json
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
FRED_MANAGER_IT_PROCESSING=1 INTEGRATION_POSTGRES_IMAGE=pgvector/pgvector:pg15 make -C apps/fred-manager test-integration CARGO_TEST_OPTS=processing_existing_worker_journey
```

It uses real Temporal, object storage and vector persistence with local model and
identity protocol fixtures. It starts no KF HTTP server and resets no existing
installation. Ordinary integration runs omit this optional heavy journey.
