---
schema: 1
title: "Prepare the Fred v3.14.0 release"
impact: none
configuration: none
configuration_reason: "Release documentation and synchronized package and chart metadata leave deployment values and defaults unchanged."
no_action_reason: "The normal release artifacts include the updated package versions. Other notes in this release describe the application upgrade steps."
---

## Applicability

Existing Fred deployments upgrading to v3.14.0.

## Prerequisites

Follow the prerequisites in the other notes in this release.

## Configuration

Release preparation requires no configuration changes.

## Upgrade

Use the published v3.14.0 artifacts and follow the rollout order in the conversation trace note.

## Validation

Confirm that the application shows the v3.14.0 release notes and that both GitHub releases include the migration guide.

## Rollback

Follow the rollback sections for the affected features. Release preparation adds no migration.

## Limitations

The other release notes describe the operational limitations.
