---
schema: 1
title: "Persist user display preferences in PostgreSQL"
impact: minor
configuration: none
configuration_reason: "No configuration key, chart value, secret or permission changes are required."
---
## Applicability

Existing Fred deployments upgrading to a release that includes personal display preferences.

## Prerequisites

Back up the Control Plane PostgreSQL database using the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Apply the Control Plane Alembic migration that creates `users_preferences` before
rolling out the new Control Plane and frontend images. No existing table is
renamed. Existing users start without a row. Their first authenticated load can
import valid display choices still present in that browser's localStorage.

## Validation

Sign in with a test account, change the theme, display mode, language and a
layout control, then reload with browser storage cleared. Check that the same
choices return and that `users_preferences` has one row for the test subject.

## Rollback

Roll back the frontend and Control Plane images normally. Leave the new table in
place so a later rollout can reuse saved choices. Dropping it discards choices
saved after the migration.

## Limitations

Browser values already erased before the upgrade cannot be recovered. Legacy
localStorage keys do not identify their owner, so the first account to import
from a shared browser may receive another person's display choices. Users can
change these choices after sign-in. Resizable pane widths are clamped to the
current viewport when rendered.
