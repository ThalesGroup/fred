---
schema: 1
title: "Guided tutorial with per-user progress and a platform switch"
impact: minor
configuration: none
configuration_reason: "Starting the tutorial at first sign-in is on by default and switched from the admin Interface page; no configuration key, chart value or secret changes."
---
## Applicability

Existing Fred deployments upgrading to a release that includes the guided tutorial.

## Prerequisites

Back up the Control Plane PostgreSQL database using the normal deployment procedure.

## Configuration

No configuration changes are required. The tutorial starts by itself at each
user's first sign-in by default; platform administrators can turn that off on the
admin **Interface** page (**Start the tutorial at first sign-in**). Either way,
users can open it anytime from the profile menu (**Tutorial**).

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
switch off on the admin Interface page, reset a test account's progress from the
dialog (**Start over**), reload, and check that nothing starts by itself while the
profile menu still offers **Tutorial**.

## Rollback

Roll back the frontend and Control Plane images normally. Leave the new columns
in place so a later rollout keeps users' progress and the platform switch.
Dropping them makes every user see the welcome tour again.

## Limitations

Progress is stored per account, not per device. A tour that changes enough to
be shown again is re-offered by raising its version in the frontend.
