---
schema: 1
title: "Keep pending administrator contacts visible on marketplace team cards"
impact: none
configuration: none
configuration_reason: "Only membership-enriched team listing contacts change; charter settings and authorization are unchanged."
no_action_reason: "Existing pending relations and user summaries are reused; normal deployment enables the display fix without data migration or client changes."
---
## Applicability

Fred deployments using the team administrator charter and marketplace.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

With the charter enabled, open the marketplace and check that a team whose
nominated administrator has not accepted the charter still shows that person's
avatar and name. Open that team as its pending administrator: if no accepted
administrator exists, the charter still replaces the team's content.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Contact avatars include pending nominations and do not confer administrator
permissions. Team detail responses still list accepted administrators only.
