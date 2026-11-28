---
schema: 1
title: "Weaver initial test and integration release"
impact: major
configuration: none
configuration_reason: "This release starts a new reporting history and enables image publication; it does not change application configuration or chart values."
---

## Applicability

Weaver 5.0.0-alpha.1 is an initial release for test and integration platforms.
It starts an independent release history with an intentional break from Swift.
No detailed Swift-to-Weaver change inventory or migration procedure is provided.

The core distribution comprises Control Plane, the frontend, Fred Agents and
Knowledge Flow's API and ingestion worker, including the optional PyMuPDF worker
image, plus the technical monitor. The Fred, Agent Pod and
Knowledge Base Helm charts are packaged by the existing chart workflow.

## Prerequisites

Use a new installation with empty application databases and dedicated storage.
Provide Kubernetes and Helm, PostgreSQL, OpenSearch, an identity provider,
Temporal, object storage and the credentials for the selected model providers.
See the matching [chart requirements](../../charts/fred/README.md#requirements).

## Configuration

Use the Weaver chart and platform-owned values and Secrets. Configure service
endpoints, identity clients, model sources and ingress for the target platform.
Do not reuse Swift application configuration or an existing Swift database.
See the [chart configuration](../../charts/fred/README.md#your-values-file).

## Upgrade

Install the versioned chart with its matching images on the new platform. Run
the chart's schema-initialization and migration hooks before starting services,
then complete platform bootstrap and provisioning. There is no in-place upgrade
from Swift or an older Weaver installation.

Version 5 branch pushes publish `v5-dev`; Swift continues using `swift-dev`. Paired
`code/v5.0.0-alpha.1` and `chart/v5.0.0-alpha.1` tags on the same commit publish
the initial release. Prereleases do not update `latest`; stable releases do.
See [image publication](../../README.md#image-publication).

## Validation

Before accepting a platform, confirm that all seven image publications and all
three chart packages succeeded. Check initialization Jobs and workload readiness,
then verify sign-in, an authorized assistant conversation, and document ingestion
and retrieval. These platform checks are operator acceptance steps; generating
this report does not execute or certify them.

## Rollback

Keep the existing Swift platform independent and available during evaluation.
Stop using the new Weaver platform if acceptance fails. Returning to Swift does
not transfer Weaver data; no cross-version data rollback is supported.

## Limitations

This alpha release is intended for test and integration, not production approval.
Resources bulk ZIP download is not available on the Weaver path (#3367).
The platform-wide activity, corpus audit and platform-data migration pages show
pending-feature notices; their Swift preview does not provide Weaver operations.
Platform provisioning remains a separate supported setup path.

Publishing artifacts does not deploy a platform. Dev tags are mutable and a failed
image matrix can leave a partial publication; use a fully published version for
platform acceptance. Later release reports cover changes since the previous
Weaver release, while fresh installation remains the supported deployment path.
