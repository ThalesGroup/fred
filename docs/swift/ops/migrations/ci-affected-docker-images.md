---
schema: 1
title: "Build only the Docker images a pull request affects"
impact: none
configuration: none
configuration_reason: "Only CI workflow and image-selection files change; no runtime or chart configuration is involved."
no_action_reason: "Only pull-request CI selection changes; images, releases and deployments are unchanged."
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

Open a documentation-only pull request and check that the Docker images run summary lists every image as skipped.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
