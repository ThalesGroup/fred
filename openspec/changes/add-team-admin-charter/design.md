## Context

See proposal.md for the motivation and specs/team-admin-charter/spec.md for the required behaviour.

Observed state on `swift` that shapes the approach:

- `team_admin` is a direct OpenFGA relation (`schema.fga`, `type team`). Exactly five permissions are `team_admin` alone: `can_update_info` and the four `can_administer_*`. `can_run_evaluations` and `can_manage_evaluation_corpus` are `team_analyst or team_admin`.
- Those five permissions are only checked in the control-plane, through two functions in `teams/service.py`. `_validate_team_and_check_permission` runs the check for team update, avatar upload, member search and every membership endpoint. `_get_team_permissions_for_user` runs one BatchCheck and returns the list the frontend reads through `useTeamCapabilities`. Knowledge-flow and fred-runtime never check them. `routing_policy/service.py` uses `can_update_info` as a stand-in for "is team admin" in its own BatchCheck, to decide who may read the routing policy.
- `team_admin` is written in five places: team creation, `add_team_member`, `grant_team_member_role`, the rescue endpoint and the import bundle. The last-admin guard and the rescue "orphaned team" check count `team_admin` relations.
- GCU acceptance lives in the fred-core `users` table as a PostgreSQL enum limited to `v1`, keyed by a UUID derived from the Keycloak subject. It is enforced by `get_current_user` in fred-core.
- Legal markdown is static frontend content: `apps/frontend/public/gcu*.md`, shadowed by any root `*.md` of the theme archive. `GcuPage` and `GdprPage` each carry their own copy of the `contrib/<brand>/<name>.<lang>.md` → `<name>.md` loading cascade.
- The current Alembic head of the control-plane is `d3f8a2c6e174`.

## Goals / Non-Goals

**Goals:**

- One place in the control-plane decides whether administrator-only team permissions are active.
- Zero added cost for users who hold no administrator-only permission.
- The OpenFGA model, fred-core and the non-control-plane services stay untouched.

**Non-Goals:**

- Enforcing the charter's content (backup administrator, monthly review, member vetting). The product records the commitment; the charter's obligations stay human processes.
- Showing other members whether an administrator has accepted.
- Fixing the GCU version enum. It is a separate defect.

## Decisions

### Gate in the control-plane permission path, not in the OpenFGA model

Keep a module-level `ADMIN_ONLY_TEAM_PERMISSIONS` next to `_validate_team_and_check_permission`, and apply the rule in the two functions above.

- In `_validate_team_and_check_permission`: after the ReBAC check has passed, if a version is configured and the requested permissions include one of the five, read the acceptance and raise `TeamAdminCharterNotAcceptedError`, mapped to 403 `team_admin_charter_not_accepted`. Running it after the ReBAC check keeps the usual 403 for non-administrators and never reads the database for them.
- In `drop_unaccepted_team_admin_permissions`, used by `_get_team_permissions_for_user` and by the routing policy read: if the checked permissions include any of the five and the acceptance is missing, drop them, and drop `can_run_evaluations` and `can_manage_evaluation_corpus` too unless the analyst-only `can_read_conversations_for_evaluation` is held. The analyst marker is part of the same BatchCheck, so no extra round trip.

A test asserts that `ADMIN_ONLY_TEAM_PERMISSIONS` equals the set of `define can_*: team_admin` lines in `schema.fga`, so a new administrator-only permission cannot silently bypass the gate.

Alternative: an intersection in the model (`team_admin and charter_signatory from organization`). Rejected for three reasons.
- The `team → organization` edge is not relied on by any team permission today and would need a backfill over every team.
- The acceptance would live in two stores, the database (the record) and OpenFGA (the enforcement), kept in sync.
- A version change would mean deleting signatory tuples in bulk.

### Keep writing the relation; do not defer it until acceptance

Alternative: store a pending nomination and write `team_admin` only once the nominee accepts. Rejected for three reasons.
- It adds a pending state to every member list and to the membership API.
- A freshly created team could have zero effective administrators, breaking the `POST /teams` guarantee of at least one.
- An existing administrator cannot be put back to pending when the version changes.

With the gate, the relation keeps meaning "nominated administrator" and the charter decides when the role's authority is active.

### One acceptance per user, keyed by Keycloak uid and version

Decided with the developer: one acceptance covers every team the user administers.

- New control-plane table `team_admin_charter_acceptances`: `user_id` (string), `version` (string), `accepted_at` (timestamptz, `utcnow`), primary key `(user_id, version)`.
- `user_id` is the Keycloak `uid` used as the OpenFGA subject, not the derived UUID of the fred-core `users` table.
- Recording uses insert-if-absent, so a repeated acceptance keeps the first time and the audit event is emitted only when a row is inserted.

Alternative: add columns to the fred-core `users` table next to the GCU ones. Rejected: it needs a fred-core change, keeps a single version with no history, and invites the same enum trap.

### Version is a free string in configuration

`app.team_admin_charter_version: str | None = None`, next to `gcu_version`. Comparing strings avoids the enum that pins `gcu_version` to `v1`.

### Acceptance read: no in-process cache

Each gated check reads one primary-key row, only when an administrator-only permission is involved. No cache: the control-plane may run several replicas, and a cached "not accepted" would keep an administrator locked out on another replica after accepting.

The dependency reaches the service through `TeamServiceDependencies.get_team_admin_charter_store` and the configuration already carried there.

### Status endpoint

Two endpoints in a new `team_admin_charter` router, under `get_current_user`, since GCU acceptance comes first:
- `GET /control-plane/v1/team-admin-charter` returns `TeamAdminCharterStatus {required: bool, accepted_at: datetime | None}`.
- `POST /control-plane/v1/team-admin-charter` records the acceptance and returns the same status.

`required` reads the acceptance first. Only when it is missing does it run one ListObjects on `can_administer_admins`, which is exactly `team_admin`, to learn whether the user administers any team. A disabled ReBAC engine yields `required = false`.

### Frontend: a pop-up in the main layout, on team pages only

`TeamAdminCharterPrompt` is mounted in `MainLayout`, which wraps the home page and every `team/:teamId/*` page.
- It reads the route's team through `useSelectedTeam`, and only queries the status and opens the shared `Dialog` when the user holds `team_admin` on that team (from `my_relations`). The home page and the personal space never show it.
- The status query refetches whenever it starts, so a promotion made by another admin is seen the next time the user opens that team.
- Later sets component state only, with no storage. `MainLayout` stays mounted while navigating, so the pop-up stays closed until the next app load.
- Accept calls the mutation, whose `invalidatesTags` covers the status and `ControlPlaneTeam`, so permissions are refetched and admin actions appear without a reload.

It does not block the app: the gate already makes administrator rights inert, and a member must not lose chat because they were nominated.

### Shared charter content and a team settings section instead of a route

- **`TeamAdminCharterContent`**: renders the markdown through the extracted `useLegalMarkdown("team-admin-charter")`, plus the 1px end sentinel, which uses the Firefox-safe `threshold: 0` from `GcuPage`. It reports when the end is reached. Both the pop-up and the new `responsibilities` section of `TeamSettingsPage` use it.
- **Section visibility**: gated on `selectedTeam.my_relations` including `team_admin`, since the permissions list no longer shows administrator status while acceptance is pending.
- **Pending notice**: shown at the top of team settings.

No standalone `/team-admin-charter` route: the charter only concerns administrators, and team settings is where they already administer.

### Markdown hook extracted from the GCU and GDPR pages

`useLegalMarkdown(name)` keeps the current candidate order and the `<!doctype` SPA-fallback rejection, and replaces both inline copies. It is its own commit, before the feature commits.

## Risks / Trade-offs

- [Enabling the setting on a live deployment suspends every administrator at once] → Acceptance is self-service and prompted on their team's pages. `TERMS_OF_USE.md` tells operators to ship the theme archive's charter before setting the version.
- [A future administrator-only check written outside the two functions bypasses the gate] → The `schema.fga` parity test catches a new `team_admin`-only permission. `REBAC.md` states that these checks must go through `_validate_team_and_check_permission`.
- [A team whose only administrators have not accepted cannot be administered, and rescue refuses because administrators exist] → Accepted: any of those administrators can unblock the team alone by accepting.
- [An administrator who chooses Later is shown actions disappearing in team settings] → The pending notice explains why and links to the Responsibilities section.
- [Migration ordering with #2649, which also parents `d3f8a2c6e174`] → Whichever PR merges second re-parents its migration onto the new head, per CLAUDE.md. No merge revision.

## Migration Plan

1. Deploy with `app.team_admin_charter_version` unset. The migration creates an empty table and behaviour is unchanged.
2. Publish a theme archive containing `team-admin-charter.md` and `team-admin-charter.fr.md`.
3. Set `app.team_admin_charter_version`. Administrators are prompted the next time they open one of their teams.

Rollback: unset the version. The table and its rows stay, and re-enabling the same version keeps past acceptances valid.
