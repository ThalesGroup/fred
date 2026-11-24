---
schema: 1
title: "Weaver project parameters and team projects list"
impact: minor
configuration: none
configuration_reason: "Project parameters are space data edited in the application; no environment variable, secret or chart value is added or changed."
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
SQLx migration `0054_project_parameters.sql`, then deploy matching Control Plane
and frontend versions. Existing projects keep no description, no avatar, the
inherited conversation retention, hidden visibility and invitation-only joining,
so nothing becomes visible until a project Owner changes it.

A project's direct Owner now finds Parameters first in the project's settings
(name, description, avatar, conversation retention, visibility and joining). For a
project, visibility and open joining address members of the parent team. A team's
Projects page lists its visible projects plus the person's own, with a Join action
on open ones. A team Owner without a content role also lists them and lands on
that page, but joining still requires a content role in the team. A project
without its own conversation retention follows its parent team's configured value,
then the lifecycle policy.

## Validation

As a project Owner, open the project's settings gear: it lands on Parameters. Make
the project visible with open joining. As another member of the parent team, open
the team's Projects page, join the project and verify it opens.

## Rollback

Roll back Control Plane and frontend together. An older Control Plane binary
rejects the newer SQLx migration history; restore a matching pre-upgrade database
backup with the prior binaries. Do not remove migration receipts manually.

## Limitations

A team's retention change applies only to future deletion requests in its
projects; accepted requests keep their deadline.
