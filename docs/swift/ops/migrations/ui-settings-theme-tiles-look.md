---
schema: 1
title: "Restore the UI settings theme tiles' look"
impact: none
configuration: none
configuration_reason: "No configuration key, default or chart value changes."
no_action_reason: "Visual change to one admin page; theme settings, archive themes and the API are untouched."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

On **Platform administration → User interface**, each theme tile now shows the
switch, the theme name, then its light and dark preview, aligned across tiles
and marked with light/dark mode icons. The default theme reads as a plain
"Default" label with a check icon and a primary border, instead of a disabled
button. Archive themes, their previews and every setting behave as before.

## Validation

Open **Platform administration → User interface**: previews line up whatever
the theme name length, and only the default tile has the primary border and
label.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No limitation applies: the change is presentational and every theme,
including archive themes, gets the same tile.
