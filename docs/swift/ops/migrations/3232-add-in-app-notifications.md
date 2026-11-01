---
schema: 1
title: "In-app notifications"
impact: minor
configuration: none
configuration_reason: "Only two new control-plane tables, one nullable column, new routes and a lifecycle step change; no configuration keys, environment variables or Helm values change."
---

## Applicability

Every Fred deployment. The control-plane database gains the `notifications`
and `disabled_notification_types` tables and the nullable
`agent_marketplace_entry.published_by` column.

## Prerequisites

Back up the control-plane database, as for any schema migration.

## Configuration

No configuration changes are required.

## Upgrade

Apply the control-plane Alembic head (revision `83b81adf7450`, after
`f28c3e9ab641`) before starting the new control plane and its Temporal worker.
It rewrites no existing row. The lifecycle workflow picks up the expiry step
on its next tick.

## Validation

Have one editor publish an agent and a second editor of the same team change
it: the publisher's `GET /control-plane/v1/notifications/summary` returns
`unseen_count: 1`.

## Rollback

Downgrading `83b81adf7450` drops the two tables and `published_by`:
notifications, turned-off types and recorded publishers are lost. Marketplace
entries are unaffected.

## Limitations

Entries published before the upgrade have no recorded publisher and notify
nobody until their next republish; there is no backfill.
