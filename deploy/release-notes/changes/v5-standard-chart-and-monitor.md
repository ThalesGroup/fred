---
schema: 1
title: "Install the v5 platform and monitor from the standard chart"
impact: minor
configuration: production
configuration_reason: "The chart enables the core v5 workloads, SQL initialization and monitor, supplies their shared wiring, and requires platform-owned infrastructure and Secrets."
after: [v5-development-image-tag]
---

## Applicability

Fresh v5 test and integration installations. No upgrade from Swift or an earlier
Weaver database is supported. Swift's branch and publication flow are unchanged.

## Prerequisites

Provision the external services, fresh SQL database/roles, buckets, trusted CAs,
identity clients and Secrets in the [chart requirements](../../charts/fred/README.md#requirements).
The optional PostgreSQL bootstrap hook needs administrator credentials; application
pods and monitor must use their own component credentials.

## Configuration

Use the standard `fred` chart with platform overrides only. It enables Fred Agents,
its preparation worker, document processing and monitor, and initializes Control
Plane and runtime/capability schemas in order. The retired `control-plane-worker`
entry is removed: lifecycle work runs in Control Plane's `serve` process.

Supply addresses, ingress/TLS, model sources and credentials, storage and sizing.
See the [external Secret contract](../../charts/fred/README.md#external-secret-contract).
Monitor uses `fred-secrets/POSTGRES_MONITOR_DATABASE_URL` for the dedicated
`fred_monitor` login, with `cp_read` search path; never use owner credentials.
The bootstrap token remains an explicit Control Plane Secret reference.

The runtime has no Kubernetes API permissions or kubeconfig mount by default.
Deployments needing Kubernetes tools must explicitly supply scoped access.
When selecting OpenSearch for Knowledge Flow, supply `type` and `index`; remove
obsolete `collection_name: null` entries from overlays. API and worker must select
the same corpus. Runtime object storage defaults to a shared private S3 bucket.

## Upgrade

Install on a fresh platform using a fully published chart version and its matching
images. Monitor now participates in the existing image publication workflow,
including `v5-dev`. Dev tags remain mutable; publication alone does not roll pods.

## Validation

Check ordered initialization Jobs, workload readiness and monitor image pulls.
Verify platform bootstrap, a conversation, document ingestion/search and capability
preparation. A platform administrator should see the monitor status; unauthorized
users must not obtain it. Rendering checks do not establish live acceptance.

## Rollback

Stop using the new platform if acceptance fails. Keep Swift separate; no transfer
or rollback of Weaver data into Swift is supported.

## Limitations

No infrastructure or platform deployment is performed by image/chart publication.
The first alpha must be published before it can be pinned by the deployment factory.
Operational acceptance belongs to the target platform's operator.
