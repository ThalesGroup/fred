---
schema: 1
title: "Edit an organization's name, owner and administrator from the platform API"
impact: none
configuration: none
configuration_reason: "Adds two Control Plane routes under the existing platform-owner authority; no configuration keys or defaults change."
no_action_reason: "No SQL migration or OpenFGA model change: the edit updates the existing space row and direct role tuples, so a normal deployment is enough."
---
## Applicability

Existing Fred 5.x (weaver) deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

As a platform owner, call `PATCH /control-plane/v1/admin/organizations/{id}` with a new
name, owner or administrator username, then check that
`GET /control-plane/v1/admin/organizations/{id}` returns the new values.

## Rollback

Use the normal rollback procedure; this change introduces no data migration. Names and
roles changed through the API stay as they were edited.

## Limitations

Renaming an organization changes the name a provisioning bundle uses to find it: a
later bundle import that still declares the old name creates a separate organization.
