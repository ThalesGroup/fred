## Context

After `platform-type-and-explicit-team-kind`, `organization:fred` holds only the
stored `team#organization` edge, plus the inert platform tuples left there by
the step 1 copy. Team governance is gated by `platform` permissions
(`can_create_team`, `can_list_all_teams`, `can_delete_team`,
`can_rescue_team_admin`) in `teams/service.py`. No organization registry
exists, and nothing records which organization a person belongs to.

## Goals / Non-Goals

**Goals:** organization as a configured tenant; `org_admin` takes over team
governance; `team_manager` disappears; no holder loses an action.

**Non-Goals:** creating further organizations (no API, no UI); organization
content and `org_editor`; an organization view for users; deleting the inert
tuples (see Decision 6).

## Decisions

1. **Registry plus ReBAC, as for teams.** An `organization` table holds
   identity (id, name). ReBAC holds the relations: `member`, `org_admin`, and
   the stored team edge. `teammetadata.organization_id` is not null after
   reconciliation. This mirrors the team model rather than adding a second shape.
2. **Configuration `initial_organization: {id, name}`**, required, documented
   as "created on first start, and joined by every new account". It lives in
   the control-plane configuration, chart values and generated schemas. The
   word "initial" stays accurate once more organizations exist.
3. **Membership is written once per account.** The account's first
   authenticated request writes `member` idempotently, at the point where the
   account status check already runs. A per-process memo avoids repeating the
   write; it is only an optimization, so separate replicas stay correct.
4. **Governance gates move to the organization.** The four team-governance
   permissions become `organization` permissions held by `org_admin`, checked
   against the target team's organization, so a direct id from another
   organization is denied. `POST /teams` keeps its shape: the team lands in the
   caller's organization (MG4). `feature_manager`'s roster stays a `platform`
   permission.
5. **Granting `org_admin`.** The first one is named by `platform_admin` (for
   the initial organization: the upgrade, Decision 7). After that, `org_admin`
   manages `org_admin`s, as `team_admin` does for its team. On the admin pages,
   it is shown where `team_manager` used to be.
6. **No deletion in release 1.** The step 1 tuples on `organization:fred` stay
   inert, and `team_manager` tuples are ignored by a schema that no longer
   defines the role. Deleting them is a small cleanup change once release 1 has
   run in production, which keeps rollback open for the whole release.
7. **Upgrade = startup reconciliation** under the advisory lock. It creates the
   configured organization, writes the team edge for every team without one, and
   `member` for every person found in any team or platform relation. It makes
   every `platform_admin` and `team_manager` an `org_admin`. When the configured
   id differs from `fred`, existing `organization:fred` team edges are copied to
   it. Accounts not covered join at their next request (Decision 3).

## Risks / Trade-offs

- [`platform_admin` loses team governance on a fresh install] → The bootstrap
  root gets `org_admin` of the initial organization at bootstrap, so a new
  installation keeps a path to its first team.
- [A person with no relation and no request since upgrade is not yet a member]
  → Nothing reads membership in release 1 except organization isolation, which
  is moot with one organization; they join at their next request.
- [Operator forgets the new setting] → Startup fails and names it; the migration
  guide states it (minor version).

## Migration Plan

1. Operator adds `initial_organization` (migration guide).
2. Alembic: `organization` table, `teammetadata.organization_id` (nullable:
   the reconciliation fills it, since only it knows the configured id; the
   cleanup change of Decision 6 makes it not null).
3. Startup reconciliation (Decision 7).
4. Rollback: the previous version ignores the new table, column and relations;
   the step 1 tuples are still in place.
