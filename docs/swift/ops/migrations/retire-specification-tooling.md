---
schema: 1
title: "Retire repository specification tooling"
impact: none
configuration: none
configuration_reason: "Only contributor tooling, documentation, and a CI path rule change."
no_action_reason: "The application, data, API, and chart behavior of existing deployments is unchanged."
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

The Docker image selector continues to exclude documentation-only changes.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
