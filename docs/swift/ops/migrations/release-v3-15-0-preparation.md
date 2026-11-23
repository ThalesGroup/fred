---
schema: 1
title: "Prepare the Fred v3.15.0 release"
impact: none
configuration: none
configuration_reason: "Release documentation and synchronized package and chart metadata preserve deployment values and defaults."
no_action_reason: "Normal deployment installs the prepared package versions. The trace storage note records the database and rollout steps for this release."
---

## Applicability

Existing Fred deployments upgrading to v3.15.0.

## Prerequisites

Follow the trace storage prerequisites in the consolidated guide.

## Configuration

Release preparation requires no configuration changes.

## Upgrade

Use the published v3.15.0 artifacts and follow the trace storage rollout order.

## Validation

Confirm that the application shows the v3.15.0 release notes and that both
GitHub releases include the migration guide.

## Rollback

Follow the trace storage rollback procedure. Release preparation adds no migration.

## Limitations

See the trace storage note for capture compatibility and rollout limitations.
