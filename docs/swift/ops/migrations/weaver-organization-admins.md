---
schema: 1
title: "Several administrators per organization"
impact: none
configuration: none
configuration_reason: "Changes the request bodies of two existing Control Plane routes under the existing platform-owner authority; no configuration keys or defaults change."
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
call `POST` or `PATCH /control-plane/v1/admin/organizations` must send
`admin_usernames` (a list of 1 to 50 usernames) instead of `admin_username`; the
former field is now refused with 422.

## Validation

As a platform owner, open the Organizations admin page, create an organization with
two administrators, then edit it to add a third and remove one; the edit dialog shows
the saved list. `GET /control-plane/v1/admin/organizations/{id}` returns the same
administrators. Saving with no administrator is not possible.

## Rollback

Use the normal rollback procedure; this change introduces no data migration. Every
administrator granted stays an administrator after a rollback.

## Limitations

A `PATCH` replaces the whole administrator list: administrators appointed inside the
organization and absent from the list are revoked.
