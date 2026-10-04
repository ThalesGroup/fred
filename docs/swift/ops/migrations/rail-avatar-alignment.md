---
schema: 1
title: "Center the user avatar at the bottom of the navigation rail"
impact: none
configuration: none
configuration_reason: "One frontend style rule; no configuration key or default changes."
no_action_reason: "The fix ships with the frontend image; no operator or user step is needed."
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

Open the application: the user avatar at the bottom of the left navigation
rail is centered under the navigation icons.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
