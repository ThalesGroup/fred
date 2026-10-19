---
schema: 1
title: "Restore the initial T0 whitelist import action"
impact: none
configuration: none
configuration_reason: "The fix changes frontend request handling only; no configuration key or default changes."
no_action_reason: "The initial import works after the normal frontend rollout; no data migration or operator action is required."
---

## Applicability

Fred deployments where platform access is enabled and the initial T0 whitelist import has not yet completed.

## Prerequisites

The administrator must already have permission to manage platform access.

## Configuration

No configuration changes are required.

## Upgrade

Deploy the updated frontend through the normal release process. The backend and stored T0 state need no migration.

## Validation

On a deployment with T0 pending, click the initial import button. Confirm that the request reaches `/control-plane/v1/admin/platform/access/t0-import`, succeeds, and the page shows T0 as completed after refresh.

## Rollback

Use the normal frontend rollback procedure. A completed T0 import remains recorded in the database.

## Limitations

This fix covers the initial import request with an omitted body. It does not change the authorization rules or the explicit T0 refresh options.
