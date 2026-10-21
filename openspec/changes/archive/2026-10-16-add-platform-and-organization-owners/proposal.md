## Why

Fred mixes technical and business administration: `platform_admin` and space
`admin` both mean "administrator". The developer and Maxime decided on 2026-10-15
that `admin` is a business role at every level, and that technical administration
belongs to an `owner` role on the platform and on each organization. This change
defines these roles for the whole of Fred; manager implements their authorization.

## What Changes

- **BREAKING** The platform role `platform_admin` becomes `platform_owner`. Root
  bootstrap grants it. Any platform owner grants or revokes platform owners; at
  least one remains. Root has no other special protection.
- **BREAKING** The platform role `team_manager`, its `can_create_team` permission
  and delegated team creation are removed: organization admins create teams.
- Each organization gains an `owner` role: technical administration, no content
  access, no descent. Platform owners grant and revoke it; at least one remains.
  Organization owners grant and revoke organization admins, as organization admins
  already do.
- A new organization requires at least one owner and one admin; one person may hold
  both. `create-org` gives its person owner, admin and member.
- Space administration is otherwise unchanged: an admin names admins and roles in
  its space and below.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `control-plane-provisioning`: platform and organization owners replace platform
  admin and team manager.

## Impact

Tracking: [#3092](https://github.com/ThalesGroup/fred/issues/3092). Applies after
`move-space-tree-to-openfga`. Code: `apps/control-plane` (model, roles, bootstrap,
platform and space services, importer, CLI), regenerated frontend manager client,
the frontend's manager platform-authority hook and role labels. Docs: arc42 chapters
2, 3, 4, 9 and A1-A3, manager README, migration note. A local reset is required.

## Non-goals

Quotas and FinOps settings for organization owners, resource roles for agents and
prompts, Python role catalogs.

## Audit completion

The approved completion includes canonical provisioning usernames, whole-bundle
email conflict preflight, directory verification for organization owners, and
rechecking content existence under the mutation lock. These are corrections to
the new manager contract, without legacy conversion or compatibility aliases.
