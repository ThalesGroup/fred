---
schema: 1
title: "The published charts carry a README, an icon and project metadata"
impact: none
configuration: local
configuration_reason: "deploy/charts/fred/values.yaml changes only in a header comment (the README path); no value, default or schema changes, so production configuration is unaffected."
no_action_reason: "Rendered Kubernetes manifests are identical; the change only affects how registries such as Artifact Hub present the charts."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

`helm show readme oci://ghcr.io/thalesgroup/fred-helm/fred --version <version>` prints the chart's README.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
