---
schema: 1
title: "Add the Nova exercise and Weaver team membership management"
impact: none
configuration: none
configuration_reason: "Weaver membership reads and frontend management reuse the existing role tables, identity directory and authorization configuration."
no_action_reason: "Deploy updated Control Plane and frontend together through the normal deployment; no schema, grant backfill or configuration action is required."
---
## Applicability

Weaver team/project owners, including the Nova local coexistence exercise.

## Prerequisites

Python 3 and Make generate the bundle offline. Manual import requires a separately
bootstrapped Weaver platform admin and the existing provisioning services.

## Configuration

No configuration changes are required. The fixture grants no platform roles.

## Upgrade

Deploy updated Control Plane and frontend together for the membership UI. No data
migration or additional role grant is required. To prepare the optional exercise,
run `make bundle-migration` and follow the Nova fixture README before importing.
The demo command is now `make bundle-demo` (replacing `build-demo-bundle`). Both
bundle commands are available at the repository root and in `apps/control-plane`.

## Validation

The generated ZIP contains two users, Nova, Pilote and an empty project list.
Confirm the declared roles manually in Weaver after an explicit import.
The Home team list and team sidebar share role-label formatting, including Weaver
owners and combined elevated roles. This display fix changes no access rights;
the membership page now uses Weaver Manage, with separate Read for content.
An owner-only account reaches members and can manage individual cumulative roles;
no content role is granted automatically. Other legacy settings subsections resolve
to membership management and are outside this increment.

## Rollback

Rollback frontend and Control Plane together. Explicit role changes made through
the membership page persist; reverting code does not revoke those grants.
Removing the generated ZIP or reverting the generator does not undo an import.
The importer is additive; manage imported identities and spaces explicitly.

## Limitations

This fixture does not migrate Swift accounts or content. Shared SSO identities
are visible to both installations; the prefixed names require a live collision
check before a first import. The browser exercise is validated separately.
