---
schema: 1
title: "Show tool approval responses in managed chat"
impact: none
configuration: none
configuration_reason: "The frontend mirrors accepted tool approval responses using existing HITL history rows; no configuration keys or defaults change."
no_action_reason: "Normal frontend deployment is sufficient; existing HITL response records remain readable."
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

Approve or refuse a tool execution in managed chat. Confirm that the localized response appears below the confirmation card immediately and remains visible after reloading the conversation. A rejected resume must leave the question answerable without showing a response.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The response is shown after the runtime accepts the resume. A failed resume shows an error and keeps the confirmation available for retry.
