---
schema: 1
title: "In-app notifications and team join requests"
impact: minor
configuration: none
configuration_reason: "Only three new control-plane tables, one nullable column on agent_marketplace_entry, a new opt-in team access mode, new routes and a lifecycle step change; no configuration keys, environment variables or Helm values change."
---

## Applicability

Every Fred deployment. The control-plane database gains the `notifications`,
`team_join_requests` and `disabled_notification_types` tables and the nullable
`agent_marketplace_entry.published_by` column. Teams gain the opt-in access
mode `on_request`; every team keeps its current mode.

## Prerequisites

Back up the control-plane database, as for any schema migration.

Upgrade control-plane and knowledge-flow together, to the same release. The
shared team model gained the `on_request` access mode: an older knowledge-flow
fails to read a team set to On request, so do not let team admins pick that
mode while an older knowledge-flow still runs.

## Configuration

No configuration changes are required.

## Upgrade

Apply the control-plane Alembic head before starting the new control plane and
its Temporal worker. This contribution's revisions, `fe166447f3d5` (creates
`notifications` with its indexes, including plain indexes on `team_id` and
`group_key`, adds `published_by`), `77cd5dc306cf` (creates
`team_join_requests`) then `83b81adf7450` (creates the empty
`disabled_notification_types`: every notification type stays on), rewrite no
existing row. No other
operator action is needed: the lifecycle workflow picks up the expiry step on
its next tick.

## Validation

Have one editor publish an agent and a second editor of the same team change
it: the publisher's notification count (`GET
/control-plane/v1/notifications/summary`) becomes 1.

Set a public team to On request, then ask to join it as a non-member: each of
its admins' notification counts becomes 1, and accepting makes the requester a
member of the team.

In Administration > Notifications, a platform admin sees every notification
type switched on.

## Rollback

Downgrading `83b81adf7450` drops `disabled_notification_types`: every type is
sent again; notifications deleted when a type was turned off do not come back.
Downgrading `77cd5dc306cf` drops `team_join_requests` and turns every
`on_request` team back into `invite_only`, which older versions understand;
pending and refused requests are lost. Downgrading `fe166447f3d5` then drops the `notifications` table and the
`published_by` column; the notifications and the recorded publishers are lost.
Marketplace entries themselves are unaffected.

## Limitations

Entries published before the upgrade have no recorded publisher and notify
nobody until their next republish; there is no backfill.
