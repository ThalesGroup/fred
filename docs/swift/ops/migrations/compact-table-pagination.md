---
schema: 1
title: "Compact table pagination bar"
impact: none
configuration: none
configuration_reason: "Only the frontend table pagination layout changes; no configuration keys or defaults change."
no_action_reason: "Layout-only frontend change; it applies with the normal frontend deployment."
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

Open any paginated table, for example Team Resources: the pagination bar is shorter, with smaller navigation buttons and rows-per-page selector.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
