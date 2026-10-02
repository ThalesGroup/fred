## Why

Release 1, step 2 of `docs/swift/rfc/ORGANIZATIONS-AND-PROJECTS-RFC.md` (issue #2921),
built on `platform-type-and-explicit-team-kind`. Once the platform is its own
object, `organization` can become what the RFC says: a tenant, with its own
identity, members, teams and administrators.

## What Changes

- An organization is explicit data: a registry entry (id, name), with members
  and teams. Every team, personal spaces included, belongs to exactly one
  organization; every person belongs to exactly one.
- The operator configures the organization of the installation (id and name,
  no default). The configuration states that every new account joins it. A
  missing value stops the upgrade.
- New organization role `org_admin`. It governs the organization's teams
  (create, list, delete, rescue a team admin) and its `org_admin`s, with no
  access to team content.
- **BREAKING (roles):** team governance leaves the platform tier.
  `platform_admin` creates organizations and names their first `org_admin`, and
  no longer governs teams directly. `team_manager` is deleted. On upgrade, every
  `platform_admin` and `team_manager` becomes `org_admin` of the configured
  organization, so no holder loses any action.
- `feature_manager` keeps the team roster of every organization, for
  per-team capability enablement.
- No change for users. On the admin pages, `org_admin` takes the place of
  `team_manager`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `tenancy`: adds organizations as tenants, organization membership,
  `org_admin`, and the governance split between platform and organization.

## Impact

- `libs/fred-core`: ReBAC schema (`organization` relations, `team_manager`
  removed), organization registry, team registry `organization_id`.
- `apps/control-plane-backend`: team service gates, platform-role endpoints,
  account registration, configuration model, startup reconciliation, Alembic
  migration.
- `apps/frontend`: `PlatformRolesPage` and `AdminTeamsPage` (`team_manager` →
  `org_admin`), regenerated client.
- Chart values and configuration schemas: new required organization setting.
- Contracts: `REBAC.md`, `CONTROL-PLANE-PRODUCT-CONTRACT.md` §43/§51 (platform
  roles), migration guide (operator action required, minor version).
