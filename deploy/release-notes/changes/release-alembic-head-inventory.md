---
schema: 1
title: "Show Alembic migration heads in Fred release descriptions"
impact: none
configuration: none
configuration_reason: "Only release publication tooling and documentation change; no chart values, application settings or database schema change."
no_action_reason: "The section is generated from the tagged source in GitHub release descriptions; existing deployments upgrade normally without extra actions."
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

Check that both the code and chart GitHub release descriptions list every Alembic migration tree and its head.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Control Plane uses SQLx and is outside this Alembic-only inventory.
The inventory lists each Alembic migration tree's head in the tagged source, not the revision applied to a particular database.
