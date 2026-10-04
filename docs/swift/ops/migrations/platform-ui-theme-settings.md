---
schema: 1
title: "Let platform admins set the default UI theme and hide themes"
impact: minor
configuration: none
configuration_reason: "The settings are edited in the admin UI and stored in a new control-plane table; no configuration key, default or chart value changes."
---

## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Run the control-plane Alembic migration, as the chart's migration hook does on
a normal upgrade, before the new control plane serves traffic: the public
frontend configuration reads the new `platform_ui_settings` table. The table
holds no row until a platform admin saves the settings.

The public `GET /control-plane/v1/frontend/config` gains an optional
`ui_themes` field (theme ids only). Proxies that filter that response must let
it through.

## Validation

As a platform admin, open **Administration** → **User interface**, set Cobalt as
the default theme and save. In a private window, sign in as a user who never
chose a theme: the application opens directly in Cobalt.

## Rollback

Use the normal rollback procedure. The previous version ignores the
`platform_ui_settings` table; users fall back to their own theme choice.

## Limitations

A settings change applies to each user at their next load of the application,
not to sessions already open.
