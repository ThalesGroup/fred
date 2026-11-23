---
schema: 1
title: "Set the page language from the displayed language from first load"
impact: none
configuration: none
configuration_reason: "Only the frontend boot script and i18n wiring change; no configuration keys, chart values or defaults change."
no_action_reason: "The fix ships in the frontend bundle and its static boot script; no data, API or deployment step changes."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

With a browser set to French, reload Fred: `<html lang>` reads `fr` from the start of the load and the browser no longer offers to translate the page.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

A browser in English with the Fred preference set to French keeps `lang="en"` until the preference loads after login.
