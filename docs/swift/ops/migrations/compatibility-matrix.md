---
schema: 1
title: "Compatibility matrix published with each release"
impact: none
configuration: none
configuration_reason: "The change adds a release asset and a CI check; no application, chart or values setting is read or changed."
no_action_reason: "Deployments keep installing the same images and chart; the matrix is an additional file attached to each release."
---
## Applicability

Existing Fred deployments upgrading to this release, and deployment tooling that
checks a platform against a Fred release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.
Deployment tooling can download `compatibility-matrix.yaml` from the release, as
described in `deploy/compatibility/README.md`.

## Validation

The `code/vX.Y.Z` and `chart/vX.Y.Z` GitHub Releases list `compatibility-matrix.yaml`.
The output of `make compatibility-matrix` on the tagged commit gives the same ranges.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The ranges are those the client libraries' maintainers publish; they do not prove
that Fred was tested on every version in them. Temporal, ClickHouse and the pgvector
extension publish no server compatibility and appear as `unknown`.
Fred Agents locks the Langfuse Python SDK 5, which requires a Langfuse server 4.59.0
or later.
