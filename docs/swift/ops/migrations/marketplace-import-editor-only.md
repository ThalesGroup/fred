---
schema: 1
title: "Offer only teams the caller can actually write to when importing a marketplace prompt"
impact: none
configuration: none
configuration_reason: "A frontend authorization check is corrected to match the existing backend rule; no configuration key, default, or permission model changes."
no_action_reason: "Runtime APIs, persisted data, permissions, and deployment order are unchanged; normal deployment is sufficient."
---
## Applicability

Existing Fred deployments upgrading to this release, where at least one user
holds `team_admin` on a team without also holding `team_editor`.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

The marketplace UI counted `team_admin` as an editor when listing the teams a
prompt could be imported into, and when deciding whether the "remove from
marketplace" action was offered. The authorization model grants
`can_update_resources` to `team_editor` alone, so those teams were offered and
then refused by the API, one per-target error each. The UI now matches the
backend rule.

Effect for users: a team where someone holds only `team_admin` no longer
appears in the import destination list, and that team's published prompts no
longer show the unpublish action to them. Nothing that previously succeeded
stops working — only requests that were already being refused disappear. A
user who needs to import into such a team must be granted `team_editor` on it,
which a team admin can do from the team's members settings.

## Validation

Sign in as a user holding `team_admin` but not `team_editor` on a team. Open
the prompt marketplace and start an import: the team is absent from the
destination list. Grant that user `team_editor` on the team and repeat: the
team is offered and the import succeeds.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
