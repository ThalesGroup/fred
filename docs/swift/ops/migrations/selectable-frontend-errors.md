---
schema: 1
title: "Make frontend error details selectable"
impact: none
configuration: none
configuration_reason: "The change only affects how the frontend renders route errors."
no_action_reason: "The updated frontend enables selection on the route error screen without changing APIs or stored data."
---

## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. No additional operator or user action is required.

## Validation

On a frontend route error screen, select and copy the message and stack trace.

## Rollback

Use the normal frontend rollback procedure.

## Limitations

No additional migration limitations identified for this change.
