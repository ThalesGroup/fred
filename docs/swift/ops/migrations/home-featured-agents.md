---
schema: 1
title: "Advanced home page with admin-chosen featured agents"
impact: minor
configuration: none
configuration_reason: "Settings live in the control-plane database and are edited in the admin UI; no chart or application setting changes. The new homeBannerImageFile theme key is optional."
---
## Applicability
Existing deployments upgrading the control-plane and frontend.

## Prerequisites
Normal control-plane database migration privileges.

## Configuration
No configuration changes are required. Themes may optionally add
`homeBannerImageFile` and the `--home-*` CSS variables documented in the
frontend README.

## Upgrade
Use the normal deployment procedure and control-plane Alembic upgrade.
Revision `e3a9c41f7b62` adds `platform_ui_settings.home_layout` (default
`classic`) and the `platform_home_featured_agent` table. The home page is
unchanged until a platform admin selects the advanced home.

## Validation
In Administration > Interface, choose the advanced home and add a default-team
agent, then save. Home shows the featured banner and the question field; a
question opens a new conversation with that agent and is sent once.

## Rollback
Roll back application code normally; old code ignores the new column and
table. If explicitly downgrading the schema, stop the new application first,
then run the ordinary Alembic downgrade. Featured agents and the chosen mode
will be lost.

## Limitations
Only agents of the platform default teams can be featured. A featured agent
that becomes disabled, suspended or leaves the default teams is hidden from
users until it is usable again.
