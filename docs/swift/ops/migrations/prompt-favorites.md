---
schema: 1
title: "Users can mark library prompts as favorites"
impact: minor
configuration: none
configuration_reason: "No configuration key, default or secret changes; the feature is unconditional."
---

## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. The control-plane Alembic upgrade (revision
`d7822fba0d40`) creates one new, empty table, `prompt_favorite`, with a foreign
key to `prompt` and an index on `prompt_id`. No existing row is read or
rewritten, so the migration is immediate.

The table holds personal data (which prompts a user starred). Rows are deleted
with their prompt, when the user leaves or is removed from the prompt's team,
and when the user's account is deleted through `DELETE /users/{user_id}`.

New API surface, additive only: `PUT` and `DELETE
/control-plane/v1/teams/{team_id}/prompts/{prompt_id}/favorite`, and an
`is_favorite` field on prompt listings.

## Validation

After the upgrade, `alembic_version_control_plane` holds `d7822fba0d40`. In the
UI, star a prompt on the Prompts page: the star stays filled after a reload, and
the Favorites filter lists it.

## Rollback

Use the normal rollback procedure. The Alembic downgrade drops the
`prompt_favorite` table and with it every user's favorites; an older release
ignores the table if it is left in place.

## Limitations

No additional migration limitations identified for this change.
