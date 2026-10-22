---
schema: 1
title: "Delegate Platform Access administration"
impact: none
configuration: none
configuration_reason: "No configuration keys or defaults change; the authorization model gains one delegated role and permission."
---

## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

Update the OpenFGA authorization model before deploying the new control plane and frontend.

## Configuration

No configuration changes are required.

## Upgrade

Publish the updated `schema.fga` model, then deploy the control plane and frontend.
Existing role tuples and Free links remain valid. No delegated role is assigned automatically.
A platform administrator may grant `platform_access_manager` after deployment.

## Validation

Grant `platform_access_manager` to a test user and confirm they can manage
filtering, the whitelist and a Free link while being denied unrelated admin
routes. Grant `team_manager` to another test user and confirm they can create
and list teams while registry editing and Free links are denied.

## Rollback

Roll back the application before reverting the OpenFGA model. The added model
relations are inert to the older application, and no data migration is needed.

## Limitations

The new role does not grant team content or member administration.
