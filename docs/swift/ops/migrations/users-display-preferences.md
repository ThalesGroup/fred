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
renamed. Existing users start without a row and see the documented defaults.
They choose their durable display settings again after rollout. Browser values
from an older deployment are ignored and do not populate the new table.

## Validation

Sign in with a test account, change the theme, display mode, language and
sidebar state, then reload with browser storage cleared. Check that the same
choices return and that `users_preferences` has one row for the test subject.

## Rollback

Roll back the frontend and Control Plane images normally. Leave the new table in
place so a later rollout can reuse saved choices. Dropping it discards choices
saved after the migration.

## Limitations

Personal choices from old browser storage are not migrated. An absent row or
failed preference read uses defaults for that load; the next load retries the
database read. Resizable pane widths stay in localStorage, return to their
defaults if browser storage is cleared, and are clamped to the current viewport
when rendered.
