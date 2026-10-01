---
schema: 1
title: "Remove unused task tray code and frontend dependencies"
impact: none
configuration: none
configuration_reason: "The change removes unmounted frontend components, an unused static flag helper, and unused npm dependencies; deployment configuration is unchanged."
no_action_reason: "Active task pages, APIs, and stored data are unchanged; normal frontend deployment is sufficient."
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

Open the admin Tasks page and a migration task page; confirm task rows, statuses, and acknowledgements remain available.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
