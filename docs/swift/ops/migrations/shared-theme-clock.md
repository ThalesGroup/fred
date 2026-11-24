---
schema: 1
title: "Expose the local theme clock and optional daylight schedule"
impact: minor
configuration: none
configuration_reason: "The optional schedule is packaged in the theme archive selected by the existing FRONTEND_THEME_URL setting."
---

## Applicability

The clock is available after a normal frontend upgrade. The activation steps apply
only to deployments that choose to enable a schedule in a theme ZIP.

## Prerequisites

Upgrade all frontend replicas before activating an archive that uses
`localDaylight`. Earlier installers reject that catalog field.

## Configuration

To activate scheduled appearance, add local `sunrise` and `sunset` times to the
theme catalog as described in the [theme authoring guide](../../../../apps/frontend/src/rework/features/helpCenter/content/en/guides/custom-theme.md).

## Upgrade

Keep the existing archive while upgrading. To activate a schedule afterwards,
publish the new ZIP under a new object key, update the theme URL and restart the
frontend replicas.

## Validation

Inspect `<html>` for the device's current local date and time. With a scheduled
theme selected in System mode, press Shift+F8 and advance through sunset.
Check that Fred changes to Dark, then use **Use live time** to restore the live
clock. Explicit Light or Dark retains its selected palette.

## Rollback

Restore the previous archive URL and restart the frontend replicas before
downgrading to an installer that predates schedule support. Existing archives
without the schedule can stay in place during the rollback.

## Limitations

The schedule uses fixed daily times in the visitor's device time zone.
