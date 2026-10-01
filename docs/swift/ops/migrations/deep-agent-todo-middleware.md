---
schema: 1
title: "Restore Deep agent task lists"
impact: none
configuration: none
configuration_reason: "Deep runtime middleware changes; no configuration keys or defaults change."
no_action_reason: "Normal deployment restores the write_todos tool; no data or API migration is needed."
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

Ask a Deep agent to plan a multi-step task and confirm its task list appears in the chat.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
