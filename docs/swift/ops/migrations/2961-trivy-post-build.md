---
schema: 1
title: "Run PR image scans after builds with Trivy v0.75.0"
impact: none
configuration: none
configuration_reason: "Only GitHub Actions image handoff and scanner version change; deployment configuration is unaffected."
no_action_reason: "PR scans run in dedicated jobs; deployed images, APIs and data are unchanged."
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

On a PR affecting an image, verify the build uploads its image archive and the dependent Trivy job scans it and publishes its report using v0.75.0. Frontend dependency scans also use v0.75.0.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
