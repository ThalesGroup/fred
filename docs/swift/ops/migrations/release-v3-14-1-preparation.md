---
schema: 1
title: "Prepare the Fred v3.14.1 release"
impact: none
configuration: none
configuration_reason: "Release notes, the operator guide, and synchronized package and chart metadata do not change deployment values or defaults."
no_action_reason: "Normal deployment needs no additional action; the release artifacts include updated package versions, and the other notes describe the shipped application behavior."
---

## Applicability

Existing Fred deployments upgrading to v3.14.1.

## Prerequisites

No additional prerequisites beyond normal deployment.

## Configuration

No configuration changes are required.

## Upgrade

Deploy the published v3.14.1 artifacts normally.

## Validation

Confirm that Fred shows the v3.14.1 release notes and that both GitHub releases include the migration guide.

## Rollback

Use the normal rollback procedure. Release preparation adds no data migration.

## Limitations

The other notes describe the limitations of the shipped features.
