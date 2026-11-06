---
schema: 1
title: "Require team membership to list a team's sessions"
impact: none
configuration: none
configuration_reason: "Only the permission checked by the team session-list route changes; no configuration keys, defaults or schemas change."
no_action_reason: "The ReBAC schema already defines can_read_conversations for team members; the stricter check takes effect with normal deployment and needs no data or tuple migration."
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

With an account that is not a member of a public team, call
`GET /control-plane/v1/teams/{team_id}/sessions` for that team and check that it
returns HTTP 403 instead of HTTP 200. A member still gets their own sessions.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
