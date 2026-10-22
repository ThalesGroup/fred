---
schema: 1
title: "In-app notifications and team join requests"
impact: minor
configuration: none
configuration_reason: "Only two new control-plane tables, one nullable column on agent_marketplace_entry, a new opt-in team access mode, new routes and a lifecycle step change; no configuration keys, environment variables or Helm values change."
---

## Applicability

Every Fred deployment. The control-plane database gains the `notifications`
and `team_join_requests` tables and the nullable
`agent_marketplace_entry.published_by` column. Teams gain the opt-in access
mode `on_request`; every team keeps its current mode.

## Prerequisites

Back up the control-plane database, as for any schema migration.

## Configuration

No configuration changes are required.

## Upgrade

Apply the control-plane Alembic head before starting the new control plane and
its Temporal worker. This contribution's revisions, `fe166447f3d5` (creates
`notifications`, adds `published_by`) then `77cd5dc306cf` (creates
`team_join_requests`), rewrite no existing row. No other
operator action is needed: the lifecycle workflow picks up the expiry step on
its next tick.

## Validation

Have one editor publish an agent and a second editor of the same team change
it: the publisher's notification count (`GET
/control-plane/v1/notifications/summary`) becomes 1.

Set a public team to On request, then ask to join it as a non-member: each of
its admins' notification counts becomes 1, and accepting makes the requester a
member of the team.

## Rollback

Downgrading `77cd5dc306cf` drops `team_join_requests` and turns every
`on_request` team back into `invite_only`, which older versions understand;
pending and refused requests are lost. Downgrading `fe166447f3d5` then drops the `notifications` table and the
`published_by` column; the notifications and the recorded publishers are lost.
Marketplace entries themselves are unaffected.

## Limitations

Entries published before the upgrade have no recorded publisher and notify
nobody until their next republish; there is no backfill.
