---
schema: 1
title: "Fix wiki version history crash on never-saved agent rules"
impact: none
configuration: none
configuration_reason: "Only the frontend wiki history panel changes; no configuration keys or defaults change."
no_action_reason: "Frontend-only fix; existing data and APIs are unchanged, so normal deployment is enough."
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

On a team whose agent rules were never saved, open Wiki > Agent rules > Version history and check that the panel shows "No earlier versions." instead of an application error.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
