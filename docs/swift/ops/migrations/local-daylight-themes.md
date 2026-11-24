---
schema: 1
title: "Enable local sunrise and sunset for a deployment theme"
impact: minor
configuration: none
configuration_reason: "The schedule is packaged in the theme archive. Existing Helm values and FRONTEND_THEME_URL select it."
---

## Applicability

Deployments that choose to add a local daylight schedule to a frontend theme ZIP.

## Prerequisites

Use a frontend version with local daylight support on every replica before introducing a ZIP that declares a schedule.

## Configuration

The optional `localDaylight` entry in the deployment ZIP's `theme-catalog.json` provides the sunrise and sunset in local 24-hour time. The existing `FRONTEND_THEME_URL` setting selects the archive. See the [theme authoring guide](../../../../apps/frontend/src/rework/features/helpCenter/content/en/guides/custom-theme.md).

## Upgrade

Existing bundles can stay in place during the normal frontend rollout. To enable the feature, publish the scheduled archive under a new object key, update the theme URL and restart the frontend replicas.

## Validation

Open the theme in System mode. Check its local hours in user settings and check that Light and Dark can each be selected explicitly.

## Rollback

Restore the previous archive URL and restart the frontend replicas before rolling back to a frontend that predates schedule support. Its installer rejects a catalog containing the new field.

## Limitations

The schedule uses the user's local clock and fixed civil times. It does not require coordinates or an external service.
