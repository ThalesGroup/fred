---
schema: 1
title: "Organization edit no longer changes administrators"
impact: none
configuration: none
configuration_reason: "Removes one optional field from an existing Control Plane route under the existing platform-owner authority; no configuration keys or defaults change."
no_action_reason: "No SQL migration or OpenFGA model change: administrators remain direct role tuples on the organization, so a normal deployment is enough."
---
## Applicability

Existing Fred 5.x (weaver) deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required. Scripts that
call `PATCH /control-plane/v1/admin/organizations/{id}` must no longer send
`admin_username`; the field is now refused with 422. The route still renames an
organization and replaces its owner. Creation is unchanged.

## Validation

As a platform owner, open the Organizations admin page and edit an organization: the
dialog offers its name and owner, not its administrators. Change the owner and save;
`GET /control-plane/v1/admin/organizations/{id}` returns the new owner and the same
administrators as before.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

After creation, an organization's administrators are granted and revoked by its own
owners and administrators (`PUT`/`DELETE /control-plane/v1/spaces/{id}/roles/admin/{user}`).
No screen offers this yet.
