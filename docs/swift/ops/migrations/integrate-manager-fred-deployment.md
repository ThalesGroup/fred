---
schema: 1
title: "Deploy Rust manager through the standard Fred control-plane role"
impact: major
configuration: production
configuration_reason: "The control-plane image and deployments run Rust manager; the default Fred composition has five processes and three images."
---

## Applicability

The `chore/rust-rebac` checkout uses the ordinary fred-deployment-factory `swift`
contract. It deploys Rust manager API/worker as `control-plane-backend` and
`control-plane-worker`, Knowledge Flow API/worker and frontend. The Python
control-plane and fred-agents do not run. This is not full legacy API parity.

## Configuration and continuity

Configure manager and its lifecycle catalog on `applications.control-plane-backend`;
both processes share those inputs and restart when they change. Keep API/worker
image tags equal. The image named `control-plane-backend` is built from manager.
The existing `control-plane` Keycloak client and
`fred-secrets/KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET` supply directory access;
`CONTROL_PLANE_BOOTSTRAP_TOKEN` remains the bootstrap Secret key.

Retain infrastructure, `fred-secrets` and `fred-model-credentials`. Manager keeps
database `fred`, store `fred-manager` and lifecycle queue/prefix
`fred-manager-lifecycle`. The common Temporal host/namespace configure lifecycle
work without changing its queue. Cleanup remains disabled by default. The Rust
migration hook uses only `DATABASE_URL` and applies embedded SQL migrations;
it neither creates an FGA store nor bootstraps an identity.

## Upgrade

The factory validates the previous build's cached image values before building.
When upgrading from manager-named applications, first move the active cache's
`.cache/k3d-apps/fred-<id>/images.yaml` and `images.txt` to a backup directory.
Otherwise the initial lint rejects the retired application names before reaching
the build. The next command regenerates these manifests; Docker images and
cluster data are unaffected.

From the unchanged factory `swift` checkout, run:

```sh
make k3d-app APP=fred DIR=../fred
```

The Fred build hook supplies three images and the factory synchronizes `fred-app`.
The previous manager-named workloads in that same release are replaced by the
control-plane-named workloads. A separately owned `fred-manager` deployment is
refused: inspect and explicitly retire that application release while retaining
infrastructure and data before retrying. No automatic standalone transition or
data reset is performed.

## Validation and recovery

Check the five ready application Deployments and matching API/worker image
references. Verify existing accounts, consent, roles and folders through the UI.
Both `/fred-manager/v1` and `/control-plane/v1` reach manager through the frontend.
Repeat the command to verify an ordinary upgrade of the same release.

Rollout is not atomic. After a failed sync, correct its cause and repeat the same
command. Keep coordinated SQL/OpenFGA backups before upgrades; returning to an
older binary is subject to applied SQL migration compatibility. Do not run two
separately owned manager releases against the same state. Removing `fred-app`
also removes Knowledge Flow and frontend.

## Scope

UI components and generated manager paths are unchanged. Calls for APIs not yet
reconstructed may fail. Packaging does not migrate Knowledge Flow content, legacy
roles or document ingestion into manager. Docker Compose topology is unchanged.
