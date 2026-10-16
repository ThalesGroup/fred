## Why

The platform admin Teams page (`/admin/teams`) can create a team but never change it afterwards: a mistyped name, an outdated description or a departed team admin can only be fixed by the team's own admins, or not at all when the team has none left reachable. The page also stacks a full-width creation form between the default-teams setting and the team list, so the list, which is what admins come for, sits below the fold. GitHub issue #3145.

Depends on PR #3071 (issue #3067), still open on 2026-10-16: it makes the team description required (20 to 500 characters once trimmed, at creation and on edit) and already adds the description field to this page's creation form. This change builds on it and starts after it merges.

## What Changes

- **Create team in a dialog.** A "Create team" button in the page header opens a dialog with the creation fields: name, description (required, rules of #3067) and team admins. The inline creation section disappears.
- **Edit an existing team.** A platform admin opens the same dialog from an "Edit" row action in the teams table, prefilled, and changes the team's name, description and team admins in one save.
- **New registry edit route.** `PATCH /teams/{team_id}/registry`, platform admin only, accepts a new name, a new description, admins to add and admins to remove. Name and description follow the rules of `PATCH /teams/{team_id}` (trimmed, unique name with 409 on collision, description 20-500). A team always keeps at least one active team admin. Admins added follow the team administrator charter (pending until accepted). Every save writes one audit event.
- **New organization permission** `can_edit_team_registry`, held by `platform_admin` only. `team_manager` keeps creating teams but does not edit them.
- **Condensed page.** Header with the create button, the default-teams setting kept compact, then the teams table. No new design token.
- **Contract change, explicit:** REBAC.md says platform admins never reassign an existing team's admins (only the zero-admin rescue). This change makes that an audited registry action for `platform_admin`. See "Open questions for the owner", question 1.

## Capabilities

### New Capabilities

- `team-registry-administration`: what platform-level administrators may do to a team's registry entry (create, edit name, description and team admins) from the admin Teams page, and the rules those actions keep.

### Modified Capabilities

None. `team-description` (introduced by PR #3071) is reused unchanged: its length rules apply to the new route.

## Impact

- **Backend** (`apps/control-plane-backend/control_plane_backend/teams/`): one route, one request schema, one service function; the rename/description write of `update_team` is extracted into a helper both paths share.
- **fred-core**: `schema.fga` (+ `schema.fga.json`) gains `organization#can_edit_team_registry`; `OrganizationPermission` gains the matching member; schema test updated.
- **OpenAPI and generated client**: `make generate-openapi`, then `cd apps/frontend && make update-control-plane-api`; `controlPlaneOpenApi.ts` committed regenerated, never hand-edited.
- **Frontend**: `AdminTeamsPage` (page, stylesheet, test) and a new `TeamFormDialog` beside it, built on the shared `Dialog` molecule; `locales/{fr,en}/translation.json`.
- **Docs**: dated entry in `CONTROL-PLANE-PRODUCT-CONTRACT.md`; `REBAC.md` "Team registry governance" and "Delegated admin roles"; one migration note under `docs/swift/ops/migrations/`.
- **Help Center**: none. The page is admin-only and the Help Center targets end users.
- **Validation scenario**: `validation/scenarios/test_team_registry_authz.py` gains the new route.

## Open questions for the owner

1. **May a platform admin change the admins of any team, at any time?** Today the security rules forbid it on purpose: whoever names the admins of a team can name themselves, then give themselves access to the team's agents and documents. The only exception is a team left with no admin at all. *Recommendation:* allow it, for platform admins only (not team managers), with an audit event on every change. This needs the reviewer's (dimitri-tombroff) agreement because it reverses a documented rule; if refused, the dialog edits name and description only and admins stay team-managed.
2. **May a platform admin remove themselves, or the last admin?** *Recommendation:* removing oneself is allowed like any other admin; removing the last active admin is refused, the team must always keep one (same rule as team settings).
3. **Replacing the only admin by someone who has not accepted the charter yet.** That person is only "pending" until they accept, so the team would have no active admin and the save is refused. *Recommendation:* keep the refusal with a clear message ("keep the current admin until the new one has accepted the charter"); do not weaken the rule.
4. **Does a rename need the uniqueness check?** *Recommendation:* yes, the same as today when a team admin renames their team: two teams with the same name are refused.
5. **Show the description in the teams table?** *Recommendation:* yes, one truncated line under the team name in the name column, no extra column, so the page stays compact.
6. **Team managers.** *Recommendation:* they keep the "Create team" button but see no "Edit" action.
