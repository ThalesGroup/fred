---
schema: 1
title: "In-app notifications for marketplace publishers"
impact: minor
configuration: none
configuration_reason: "Only a new control-plane table, one nullable column on agent_marketplace_entry, new caller-scoped routes and a lifecycle step change; no configuration keys, environment variables or Helm values change."
---

## Applicability

Every Fred deployment. The control-plane database gains the `notifications`
table and the nullable `agent_marketplace_entry.published_by` column.

## Prerequisites

Back up the control-plane database, as for any schema migration.

## Configuration

No configuration changes are required.

## Upgrade

Apply the control-plane Alembic head before starting the new control plane and
its Temporal worker. This contribution's revision, `fe166447f3d5`, creates
`notifications` and adds `published_by`; it rewrites no existing row. No other
operator action is needed: the lifecycle workflow picks up the expiry step on
its next tick.

## Validation

Have one editor publish an agent and a second editor of the same team change
it: the publisher's notification count (`GET
/control-plane/v1/notifications/summary`) becomes 1.

## Rollback

Downgrading `fe166447f3d5` drops the `notifications` table and the
`published_by` column; the notifications and the recorded publishers are lost.
Marketplace entries themselves are unaffected.

## Limitations

Entries published before the upgrade have no recorded publisher and notify
nobody until their next republish; there is no backfill.
