---
schema: 1
title: "Show full agent card text on hover"
impact: none
configuration: none
configuration_reason: "Only frontend card title attributes change; no runtime configuration is affected."
no_action_reason: "The tooltip reads existing card fields and requires no data or deployment changes."
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

Hover over an agent card with a long name, role, or description and confirm that the full field appears in the browser tooltip.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
