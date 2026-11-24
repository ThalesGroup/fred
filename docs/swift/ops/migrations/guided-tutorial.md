---
schema: 1
title: "Guided tutorial with per-user progress and a platform switch"
impact: minor
configuration: none
configuration_reason: "The tutorial is on by default and switched off from the admin Interface page; no configuration key, chart value or secret changes."
---
## Applicability

Existing Fred deployments upgrading to a release that includes the guided tutorial.

## Prerequisites

Back up the Control Plane PostgreSQL database using the normal deployment procedure.

## Configuration

No configuration changes are required. The tutorial is enabled by default;
platform administrators can turn it off on the admin **Interface** page
(**Guided tutorial** switch). When off, it no longer starts at sign-in and the
profile menu no longer lists it.

## Upgrade

Apply the Control Plane Alembic migrations before rolling out the new Control
Plane and frontend images. They add `users_preferences.completed_tours`
(defaults to an empty map) and `platform_ui_settings.onboarding_tour_enabled`
(defaults to true). No existing column is changed. Existing users have finished
no tour, so the welcome tour starts at their next sign-in once the patch notes,
if any, are closed.

## Validation

Sign in with a test account: the welcome tour starts. Finish or skip it, reload,
and check that it does not start again and that `users_preferences.completed_tours`
records it. Open **Tutorial** in the profile menu to see both tabs. Turn the
switch off on the admin Interface page and check that the profile menu entry
disappears after a reload.

## Rollback

Roll back the frontend and Control Plane images normally. Leave the new columns
in place so a later rollout keeps users' progress and the platform switch.
Dropping them makes every user see the welcome tour again.

## Limitations

Progress is stored per account, not per device. A tour that changes enough to
be shown again is re-offered by raising its version in the frontend.
