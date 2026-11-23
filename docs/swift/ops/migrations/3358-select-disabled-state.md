---
schema: 1
title: "Show the disabled state on the shared Select"
impact: none
configuration: none
configuration_reason: "Only a frontend stylesheet changes; no backend contract, chart value or configuration file is touched."
no_action_reason: "A disabled Select now looks disabled, with the same state tokens as a disabled Button; its behavior and API are unchanged."
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

Open the settings of an existing knowledge base in a team: its read-only "Synchronized by" selector shows a dimmed border and text, no hover effect and a default cursor, in light and dark themes.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
