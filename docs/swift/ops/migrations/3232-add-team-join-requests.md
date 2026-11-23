---
schema: 1
title: "Team join requests"
impact: minor
configuration: none
configuration_reason: "Only one new control-plane table, a new opt-in team access mode, new routes and a lifecycle step change; no configuration keys, environment variables or Helm values change."
---

## Applicability

Every Fred deployment. The control-plane database gains the
`team_join_requests` table. Teams gain the opt-in access mode `on_request`;
every team keeps its current mode.

## Prerequisites

Back up the control-plane database, as for any schema migration.

Upgrade control-plane and knowledge-flow together, to the same release: an
older knowledge-flow cannot read a team set to On request.

## Configuration

No configuration changes are required.

## Upgrade

Apply the control-plane Alembic head (revision `fd4dc8d9d058`, after
`83b81adf7450`) before starting the new control plane. It rewrites no
existing row.

## Validation

Set a public team to On request, then ask to join it as a non-member: each of
its admins' `GET /control-plane/v1/notifications/summary` counts one more
notification, and accepting makes the requester a member.

## Rollback

Downgrading `fd4dc8d9d058` turns every `on_request` team back into
`invite_only` and drops `team_join_requests`: pending and refused requests are
lost.

## Limitations

No additional migration limitations identified for this change.
