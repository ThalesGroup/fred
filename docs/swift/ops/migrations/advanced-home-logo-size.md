---
schema: 1
title: "Reduce the advanced home greeting logo"
impact: none
configuration: none
configuration_reason: "Only the frontend greeting logo width changes; no configuration keys or defaults change."
no_action_reason: "The CSS update takes effect with a normal frontend deployment; data and APIs are unchanged."
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

Open the advanced home's Quick access tab and confirm the greeting logo is 80 CSS px wide.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
