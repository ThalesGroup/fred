---
schema: 1
title: "Every space role implies membership of its space"
impact: minor
configuration: none
configuration_reason: "Membership is role data in the Control Plane database; no environment variable, secret or chart value is added or changed."
---
## Applicability

Weaver deployments upgrading Control Plane and frontend. This is not a Swift
database migration.

## Prerequisites

Use the normal backup and schema-owner procedure.

## Configuration

No configuration changes are required.

## Upgrade

Run `control-plane init-schema` with the normal schema-owner identity to apply
SQLx migration `0060_space_roles_imply_member.sql`, then deploy matching Control
Plane and frontend versions. The migration adds `member` wherever a person held
owner, editor, analyst, organization admin or organization observer on a space
without it, and a deferred constraint refuses any later role holder without
membership. Platform roles are unchanged and imply no membership.

Visible effect: owners and organization admins who held no content role now
read their space's content (agents, resources, prompts) and see it in their
navigation. Granting any role also grants `member`. Revoking `member` alone
while other roles remain returns 409 `membership_removal_required`; removing a
person goes through `DELETE /control-plane/v1/spaces/{id}/members/{user}`,
which now also serves organizations and personal spaces. In member management,
`member` is no longer a role checkbox: people added without a role join as
members, and the row's Remove action takes them out of the space.

## Validation

As a team Owner without any other role before the upgrade, open the team after
the upgrade: its agents, resources and prompts are listed. In the team's member
management, add a person without selecting a role and verify they appear with
no role chip selected; remove them with Remove and verify they leave the list.

## Rollback

Roll back Control Plane and frontend together. An older Control Plane binary
rejects the newer SQLx migration history; restore a matching pre-upgrade database
backup with the prior binaries. Do not remove migration receipts manually.

## Limitations

Owners can no longer govern a space without reading its content; organization
admins remain the role that governs an organization, now as members of it.
