---
schema: 1
title: "Agents marketplace publication settings: platform default, per-team overrides and publish permissions"
impact: minor
configuration: none
configuration_reason: "Adds a control-plane table, two nullable team columns and two OpenFGA permissions; no configuration key, default or chart value changes."
---
## Applicability

Existing Fred deployments upgrading to this release. Nothing changes for users:
publication is off by default and the settings are only reachable through the
platform-admin API.

## Prerequisites

A backup of the shared PostgreSQL database, as for any release carrying an
Alembic revision. The OpenFGA store used by the control plane must accept a new
authorization model (the control plane writes it at startup, as for every
schema change).

## Configuration

No configuration changes are required. The platform default (publishing off,
5 agents per team) lives in the database, not in configuration files.

## Upgrade

1. Apply the control-plane Alembic head before starting the new Knowledge Flow
   pods: revision `b5e1c9d3a7f2` (after `93427a5fe874`) creates
   `platform_marketplace_settings` (no row seeded) and adds the nullable
   `agents_publishing_enabled` and `agents_publish_quota` columns to
   `teammetadata`. Knowledge Flow reads `teammetadata` through the shared model,
   so it needs the new columns.
2. Deploy the control plane. At startup it writes the updated OpenFGA model,
   which adds the `can_publish_marketplace_agents` (team editors) and
   `can_unpublish_marketplace_agents` (team editors and team admins)
   permissions on `team`. No relation is added and existing tuples are
   untouched.

## Validation

- `alembic heads` on the control plane shows `b5e1c9d3a7f2` as the single head.
- As a platform admin, `GET /control-plane/v1/admin/marketplace-settings`
  answers the built-in default (publishing off, quota 5) and every team
  following it; a team admin gets 403.

## Rollback

Roll back the images, then `alembic downgrade 93427a5fe874` on the control plane
if the schema must go back too: it drops `platform_marketplace_settings` and the
two `teammetadata` columns, so every marketplace setting is lost.

## Limitations

Platform exports do not carry the marketplace settings.
