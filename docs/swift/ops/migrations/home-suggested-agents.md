---
schema: 1
title: "Suggest team agents on the home page until the user has used one"
impact: none
configuration: none
configuration_reason: "Only the home page agent row (frontend component, styles, translations) changes; no configuration keys or defaults change."
no_action_reason: "The suggestions reuse the existing recent-agents preset and team agent listing; no data, API or permission changes, so normal deployment is enough."
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

Log in as a user who has never used an agent: the home page shows "Agents available to you" with the enabled agents of their teams. After a conversation with one agent, the section shows "Recently used agents" instead.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
