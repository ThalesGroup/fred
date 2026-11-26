# Release report - v5.0.0-alpha.1

Report baseline: `f50b9a8ea8b88cac99205e7cffd2bd9eee8eef0b`
Operational impact: **major** (minimum version: `5.0.0`).

Fresh installation required. Upgrades from Swift or an earlier Weaver are not supported. Customer-specific values remain in private deployment repositories; the matching Fred chart is the configuration reference.

This initial report starts a new release history; it does not reconstruct the Swift-to-Weaver changes.

## Weaver initial test and integration release

Impact: **major** - [Source](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/release-notes/changes/weaver-initial-release.md)

### Applicability

Weaver 5.0.0-alpha.1 is an initial release for test and integration platforms.
It starts an independent release history with an intentional break from Swift.
No detailed Swift-to-Weaver change inventory or migration procedure is provided.

The core distribution comprises Control Plane, the frontend, Fred Agents and
Knowledge Flow's API and ingestion worker, including the optional PyMuPDF worker
image, plus the technical monitor. The Fred, Agent Pod and
Knowledge Base Helm charts are packaged by the existing chart workflow.

### Prerequisites

Use a new installation with empty application databases and dedicated storage.
Provide Kubernetes and Helm, PostgreSQL, OpenSearch, an identity provider,
Temporal, object storage and the credentials for the selected model providers.
See the matching [chart requirements](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/charts/fred/README.md#requirements).

### Configuration

Use the Weaver chart and platform-owned values and Secrets. Configure service
endpoints, identity clients, model sources and ingress for the target platform.
Do not reuse Swift application configuration or an existing Swift database.
See the [chart configuration](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/charts/fred/README.md#your-values-file).

### Upgrade

Install the versioned chart with its matching images on the new platform. Run
the chart's schema-initialization and migration hooks before starting services,
then complete platform bootstrap and provisioning. There is no in-place upgrade
from Swift or an older Weaver installation.

Version 5 branch pushes publish `v5-dev`; Swift continues using `swift-dev`. Paired
`code/v5.0.0-alpha.1` and `chart/v5.0.0-alpha.1` tags on the same commit publish
the initial release. Prereleases do not update `latest`; stable releases do.
See [image publication](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/README.md#image-publication).

### Validation

Before accepting a platform, confirm that all seven image publications and all
three chart packages succeeded. Check initialization Jobs and workload readiness,
then verify sign-in, an authorized assistant conversation, and document ingestion
and retrieval. These platform checks are operator acceptance steps; generating
this report does not execute or certify them.

### Rollback

Keep the existing Swift platform independent and available during evaluation.
Stop using the new Weaver platform if acceptance fails. Returning to Swift does
not transfer Weaver data; no cross-version data rollback is supported.

### Limitations

This alpha release is intended for test and integration, not production approval.
Publishing artifacts does not deploy a platform. Dev tags are mutable and a failed
image matrix can leave a partial publication; use a fully published version for
platform acceptance. Later release reports cover changes since the previous
Weaver release, while fresh installation remains the supported deployment path.

## Identify version 5 development images by their major version

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/release-notes/changes/v5-development-image-tag.md)

### Applicability

Development platforms following the images published from the `weaver` branch.
Versioned releases and Swift's `swift-dev` publication are unchanged.

### Prerequisites

Wait for all enabled `v5-dev` image publications to succeed before updating a platform.

### Configuration

In platform-owned values, replace `weaver-dev` with `v5-dev` wherever it is used
as `applications.<name>.image.tag`. Keep component repository names unchanged.
Versioned deployments retain their exact release tags and matching chart.

### Upgrade

Apply the updated values and arrange an image refresh and rollout. The old
`weaver-dev` alias is no longer published; its existing images remain in GHCR.
See the [publication conventions](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/README.md#image-publication).

### Validation

Check that the rendered workloads select `v5-dev` and that their image revisions
match the successful publication's source commit. A tag rename alone does not
restart existing workloads.

### Rollback

Restore the previously accepted image digests or an explicit release version.
No database change is introduced by this publication rename.

### Limitations

This change does not rename branches, namespaces, databases or platform URLs.
It does not deploy a platform. `v5-dev` remains mutable and is intended for
development; use exact release versions for preproduction and production.

## Install the v5 platform and monitor from the standard chart

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/release-notes/changes/v5-standard-chart-and-monitor.md)

### Applicability

Fresh v5 test and integration installations. No upgrade from Swift or an earlier
Weaver database is supported. Swift's branch and publication flow are unchanged.

### Prerequisites

Provision the external services, fresh SQL database/roles, buckets, trusted CAs,
identity clients and Secrets in the [chart requirements](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/charts/fred/README.md#requirements).
The optional PostgreSQL bootstrap hook needs administrator credentials; application
pods and monitor must use their own component credentials.

### Configuration

Use the standard `fred` chart with platform overrides only. It enables Fred Agents,
its preparation worker, document processing and monitor, and initializes Control
Plane and runtime/capability schemas in order. The retired `control-plane-worker`
entry is removed: lifecycle work runs in Control Plane's `serve` process.

Supply addresses, ingress/TLS, model sources and credentials, storage and sizing.
See the [external Secret contract](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/charts/fred/README.md#external-secret-contract).
Monitor uses `fred-secrets/POSTGRES_MONITOR_DATABASE_URL` for the dedicated
`fred_monitor` login, with `cp_read` search path; never use owner credentials.
The bootstrap token remains an explicit Control Plane Secret reference.

The runtime has no Kubernetes API permissions or kubeconfig mount by default.
Deployments needing Kubernetes tools must explicitly supply scoped access.
When selecting OpenSearch for Knowledge Flow, supply `type` and `index`; remove
obsolete `collection_name: null` entries from overlays. API and worker must select
the same corpus. Runtime object storage defaults to a shared private S3 bucket.

### Upgrade

Install on a fresh platform using a fully published chart version and its matching
images. Monitor now participates in the existing image publication workflow,
including `v5-dev`. Dev tags remain mutable; publication alone does not roll pods.

### Validation

Check ordered initialization Jobs, workload readiness and monitor image pulls.
Verify platform bootstrap, a conversation, document ingestion/search and capability
preparation. A platform administrator should see the monitor status; unauthorized
users must not obtain it. Rendering checks do not establish live acceptance.

### Rollback

Stop using the new platform if acceptance fails. Keep Swift separate; no transfer
or rollback of Weaver data into Swift is supported.

### Limitations

No infrastructure or platform deployment is performed by image/chart publication.
The first alpha must be published before it can be pinned by the deployment factory.
Operational acceptance belongs to the target platform's operator.
