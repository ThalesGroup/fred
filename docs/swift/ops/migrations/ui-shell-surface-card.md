---
schema: 1
title: "Render pages in one surface card with input-device navigation"
impact: none
configuration: none
configuration_reason: "Frontend change only; no configuration keys or defaults change."
no_action_reason: "Layout and styling of the application shell only; nothing to configure or migrate."
---

## Applicability

Existing deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy normally; no additional operator or user action is required.

## Validation

Open any page: it sits in one rounded card beside the navigation. On a touch device the rail shows labelled items; under 768px the navigation moves to a bottom bar.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
