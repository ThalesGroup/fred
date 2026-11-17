---
schema: 1
title: "Attach the complete Alembic revision inventory to Fred releases"
impact: none
configuration: none
configuration_reason: "Only release publication tooling and documentation change; no chart values, application settings or database schema change."
no_action_reason: "The inventory is generated from the tagged source and attached to GitHub releases; existing deployments upgrade normally without extra actions."
---
## Applicability

Fred releases published after this change.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Check that both the code and chart GitHub releases attach `alembic-revisions.md` and that it lists every migration-bearing component and its head.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The inventory lists revisions shipped in the release, not revisions applied to a particular database.
