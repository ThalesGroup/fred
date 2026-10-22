---
schema: 1
title: "Refresh Free link management when opened"
impact: none
configuration: none
configuration_reason: "Only frontend query timing and presentation change; no configuration keys or defaults change."
no_action_reason: "APIs, data and permissions are unchanged; normal frontend deployment applies the fix."
after: [3211-compose-chart-registrations]
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

As a platform administrator, open Administration > Teams > Manage links. The
history stays visible while the dialog is open and refreshes when reopened.
Opening a link's joiner history fetches its current list without periodic polling.
Use Refresh in the joiner dialog; its list and the Opens count in the invitation
history update when the requests complete.

## Rollback

Use the normal frontend rollback procedure; no data migration is involved.

## Limitations

Changes made by another administrator appear when the manager or joiner dialog is
reopened, when Refresh is used in the joiner dialog, or when an affected query is
invalidated by an action in this session.
