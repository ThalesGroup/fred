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
image. Monitor is not published by this image workflow. The Fred, Agent Pod and
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

Branch pushes publish `weaver-dev`; Swift continues using `swift-dev`. Paired
`code/v5.0.0-alpha.1` and `chart/v5.0.0-alpha.1` tags on the same commit publish
the initial release. Prereleases do not update `latest`; stable releases do.
See [image publication](https://github.com/ThalesGroup/fred/blob/code/v5.0.0-alpha.1/deploy/README.md#image-publication).

### Validation

Before accepting a platform, confirm that all six image publications and all
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
