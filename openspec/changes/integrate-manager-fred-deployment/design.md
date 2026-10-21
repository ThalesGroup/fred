## Context

Factory swift 9d7d4d0 is clean and unchanged. It selects Fred's chart/build, supplies control-plane instance values and secret references, enables its migration Job and probes its bootstrap endpoint. Current fred-app instead contains manager-named API/worker resources. The developer approved retaining the deployment role while replacing its Python implementation.

## Goals / Non-Goals

One ordinary k3d command and no special factory branch. Preserve UI and persistent identities. Do not run k3d, reset data, reconstruct missing product APIs or ingest documents.

## Decisions

1. Keep control-plane-backend/control-plane-worker as deployment names and the control-plane-backend image repository. Build that image from apps/control-plane in both local build and CI. Remove the separate manager image publication entry and standalone application keys.
2. Replace the two Python chart application blocks with Rust commands, mounts, probes and configuration. Reuse the existing control-plane Keycloak client and Secret key. Manager schema validates consumed fields; legacy factory fields for unreconstructed capabilities remain accepted but do not grant those capabilities.
3. Keep the public manager route used by generated slices. The frontend gateway forwards it to the control-plane service under its configured API prefix. Factory bootstrap guidance continues to use the control-plane route.
4. Honor factory migration enablement using a database-only Rust migration command and the embedded SQL migrations. Disable the Python scale-down hook. It must need neither mounted release ConfigMaps nor Keycloak/OpenFGA credentials.
5. Preserve database/schema, OpenFGA store control-plane, lifecycle queue/prefix control-plane-lifecycle and bootstrap/consent data. Forward shared scheduler.temporal connection settings to lifecycle configuration at the chart boundary. API and worker consume the same configuration/catalogue and restart together on changes.
6. Helm replaces old manager-named resources in the same fred-app release. A still-independent manager release must be explicitly retired by its operator first; reject coexistence when detected rather than deleting another release automatically. No product build hook may mutate the cluster.

## Risks / Trade-offs

- Image naming alone is insufficient: verify the real unchanged factory overlay, Rust migration command and nginx routing, including query strings.
- A deployment rename must not reset authorization or task identities: assert these in rendered configuration and reconcile reset classification.
- Broad and deployed acceptance remain developer-owned. Use focused rendering/build/configuration/proxy tests and an independent read-only review.

## Migration Plan

The developer runs make k3d-app APP=fred DIR=../fred from the unchanged factory. Upgrade the existing fred-app release in place, then repeat for convergence. Retain the previous chart/images for recovery; never reset infrastructure or migrate manager data into the old Python model.
