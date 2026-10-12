---
schema: 1
title: "Shared UI primitives: menu item tooltips, icon and role chip sizes, dialog footer focus"
impact: none
configuration: none
configuration_reason: "Frontend shared components only; no configuration keys, defaults or chart values change."
no_action_reason: "No API, data or permission change; the updated components take effect with the normal frontend deployment."
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

On a team's Resources page, open the menu of a document that is still being
processed: hovering the greyed **Delete** item shows why it is disabled in a
tooltip. The team members table shows the smaller role chips.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
