## Context

The accepted UI restoration is local commit `4510d2a95`. `AdminTeamsPage` supplies reusable DataTable, PageHeader, TextInput, Button, Separator and layout styles. Manager has an operator-only `create_organization` (one person gets owner/admin/member), exact Keycloak username resolution, platform-owner checks, one-organization attachment checks and guarded publication. Its existing `/admin/teams` registry is metadata-only. No organization HTTP registry/creation exists.

## Goals / Non-Goals

Use the same administration panel and existing UI components. Create only the requested governance roles; reuse existing space storage and FGA authority. No directory search redesign, account creation, organization content browsing, organization switching, deletion UI, or broad business migration. Exact existing usernames are the initial form contract; missing identities must be created through the existing registration/provisioning journey.

## Decisions

- Add `GET /admin/organizations?after=<uuid>` returning `{items, next_cursor}` (100 active organizations, SQL UUID keyset with 101-row lookahead) and `POST /admin/organizations` accepting name, owner_username, admin_username. Names use existing space validation; usernames resolve exactly through the configured matching Keycloak realm. Both endpoints require personal admission and platform ownership, including owners without organization membership. The registry displays names using the team page's table; it grants no content access and does not enumerate user rosters.
- Reuse the existing organization constructor/publication path through a private helper. Keep the operator CLI's owner/admin/member initialization. HTTP creation grants Owner to the selected owner and Admin to the selected administrator, and no content or personal-space role. The same person may hold both. The caller receives no implicit grant.
- Check caller authority before directory access and recheck after acquiring the platform lock and capturing its FGA guard. Resolve known target identities before locking; under the platform lock, revalidate both attachments and name uniqueness, initialize the new organization guard, capture both guards, then persist the SQL row and guarded FGA roles with audit caller. SQL commit happens only after FGA publication; orphan tuples on uncommitted UUIDs grant no business authority, as in existing creation. Conflicting names remain conflicts (no implicit replay success).
- Registry cost: one higher-consistency `Check(user, owner, platform:root)`, one bounded SQL query, no FGA Reads, ListObjects, roster or Keycloak lookups and no SQL advisory lock. Its cost scales with page size, not membership/document volume.
- Creation cost: two owner Checks (preflight and guarded recheck), one new-guard Write (two tuples), two guard-version Reads, one paginated `Read(user:<target>, object=space:)` per distinct target plus existing placement Reads (one/team or personal, two/project), and one final guarded Write (two roles plus two guard-version insert/delete pairs, six tuple operations). Read pages use the existing FGA pagination. SQL holds the platform advisory lock across guard reads, current authorization/attachment checks and publication, never Keycloak lookup. Cost depends on the two targets' memberships/placement, not all users or documents; repeated target is resolved/checked once. Server-side Check evaluation is separate from client RPC count. Focused tests assert the empty-target request budget and paginated registry; no scalability claim.
- Mount a manager-authorized platform route boundary after admission. Owner landing is `/admin/organizations`; only Organizations, Provisioning and the existing standalone account/legal/release routes are reachable in this area. Even if the account also holds business roles, team/home/marketplace URLs lead back to Organizations. A distinct organization-entry link is deferred. Ordinary users retain the original route inventory and business components.
- Reuse navigation renderers/styles; isolate existing business bootstrap, task/charter and announcement consumers behind the business branch. Preserve shared account UI; skip Python avatar/announcement enrichment in the platform area. Authority errors expose retry and never mount the business area as fallback. Registry errors hide stale rows; successful creation refreshes the first page without automatic mutation replay.

## Risks / Trade-offs

- Mixed roles can leak business navigation: test owner with team roles and direct URLs, plus ordinary-member parity.
- Late responses can affect a different account: retain session cache reset, gate current manager authority, ignore mutation completion after page unmount.
- Unknown identity, duplicate name, existing attachment or revocation while waiting must produce explicit errors without a new committed organization. Test these with real disposable SQL/FGA and the existing identity fixture.
- Exact usernames are simpler than a directory picker and avoid an unrelated new search API. The UI labels this clearly; it neither creates accounts nor accepts fabricated subject mappings.

## Migration Plan

Regenerate manager OpenAPI and only its frontend client. No migration or grant rewrite. Deploy manager and frontend together through the factory after focused validation. Rolling back the frontend removes the new page without deleting organizations or grants. Keep commits on the requested branch; do not push without agreement. The developer's global test campaign remains deferred.
