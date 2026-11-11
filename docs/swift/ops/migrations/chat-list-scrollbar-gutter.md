---
schema: 1
title: "Chat list scrollbar sits in the list's right padding"
impact: none
configuration: none
configuration_reason: "Only the sidebar chat list stylesheet changes; no configuration keys or defaults change."
no_action_reason: "Pure CSS change in the frontend; data, APIs and deployment order are unchanged."
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

Open a team with enough conversations to scroll the sidebar list and check that the scrollbar sits in the right margin without narrowing the rows.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
