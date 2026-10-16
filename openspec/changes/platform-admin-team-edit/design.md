## Context

See proposal.md for why. Current state on `swift` (e980c956a), plus the #3067 work in the same PR:

- `POST /teams` (`create_team`) is gated on `can_create_team` (`platform_admin or team_manager`) and writes the first admins through `resolve_granted_team_relation` (charter: `pending_team_admin` until accepted). PR #3071 adds the required `description`.
- `PATCH /teams/{team_id}` (`update_team`) is gated on team `can_update_info` = `team_admin` only. It already carries the rename rules of contract §47 (trim, `get_by_name` pre-check, `IntegrityError` → 409, rename log line) and, with #3071, the description rules (`TeamDescription`, `reject_null_description`).
- Admin changes go through `POST/DELETE /teams/{id}/members/{uid}/roles`, gated on team `can_administer_admins` = `team_admin`, one role per call, guarded by `_ensure_team_keeps_at_least_one_admin` under `_team_member_role_lock_key`.
- `schema.fga` deliberately gives platform roles no team relation (RFC §24.2/§24.7). `POST /teams/{id}/rescue-admin` (`can_rescue_team_admin`) is the only registry action touching admins, and only on a team with zero `team_admin`. REBAC.md: "Never generalize this into platform_admin can reassign any team's admin at any time".
- `AdminTeamsPage.tsx` renders: default-teams section (platform admin), inline create section, teams table (name, admins avatars, optional platform-access columns).
- Shared `Dialog` molecule (`shared/molecules/Dialog`) exists; `TeamSettingsParameters` edits name/description inline with save-on-blur and is not a dialog form, so it is not reused.

## Goals / Non-Goals

**Goals:** one route and one dialog covering create and edit; no rule duplicated between the team-admin and platform-admin edit paths.

**Non-Goals:** editing visibility, joining mode, avatar, retention or editor/analyst roles from the admin page; changing team-admin self-service; removing `rescue-admin` (it becomes a subset of the new route; a deletion candidate for a separate PR once this one is accepted).

## Decisions

**D1. New organization permission `can_edit_team_registry: platform_admin`.** Mirrors `can_delete_team` and `can_rescue_team_admin`: a registry capability, no standing team relation. Alternatives: reuse `can_create_team` (would hand `team_manager` the right to appoint themselves admin of any existing team, a wider escalation than creating an empty team); reuse `can_manage_platform` (the catch-all REBAC.md carved narrow surfaces out of). Agreed (owner decision 1).

**D2. New route `PATCH /teams/{team_id}/registry`, not a widened `PATCH /teams/{team_id}`.** The team PATCH also carries visibility, joining mode, avatar and retention, which stay team self-service. Body `EditTeamRegistryRequest`: `name?`, `description?` (same validators as `UpdateTeamRequest`), `add_admin_ids: list[str] = []`, `remove_admin_ids: list[str] = []`. Response `TeamWithPermissions`, built like `create_team` without the `CAN_READ` gate (the caller is not necessarily a member). Not reusing the per-role routes: they are gated on team permissions the platform admin does not hold, and the dialog needs one atomic save.

**D3. Admin changes as a diff, not a replacement list.** `Team.admins` lists active `team_admin` only, so a full-set replace would silently revoke pending nominations the dialog never displayed, and would clobber a concurrent change by a team admin. The frontend computes added and removed ids against the roster it opened with.

**D4. One shared metadata write.** The rename/description part of `update_team` (name no-op, pre-check, `IntegrityError` → `TeamAlreadyExistsError`, rename log) moves into a private helper both `update_team` and the new service call. Extraction, not a copy.

**D5. Order of writes.** Under `advisory_lock(_team_member_role_lock_key(team_id))`: read admins with `HIGHER_CONSISTENCY`; refuse (409, `TeamAdminConstraintError`) when the resulting active `team_admin` set is empty; write relations (add via `resolve_granted_team_relation`; remove `team_admin`/`pending_team_admin` and add a direct `team_member` when the user holds no other role, like `revoke_team_member_role`); then write metadata. A metadata 409 after relation writes is avoided by running the name pre-check before any relation write; the residual race (concurrent rename between pre-check and upsert) returns 409 with admins already changed, logged, and accepted as for `update_team`. Invalidate the team relations cache after writes.

**D6. Audit.** `emit_audit_log("team.registry.edited", actor_uid=..., team_id=..., changed_fields=[...], admins_added=[ids], admins_removed=[ids])`. Ids only, no names or emails.

**D7. Frontend.** `TeamFormDialog.tsx` beside `AdminTeamsPage.tsx`, props `mode: "create" | "edit"`, `team?`, `onClose`. Built on `Dialog` (`confirmDisabled` while invalid). Fields: `TextInput` name; `TextArea` description with its guidance sentence in `description` (above the field), counter and error from `@core/utils/teamFields.ts` (#3071); admins `Autocomplete` (`useSearchCandidateTeamAdminsQuery`) + `Chip` list. Content `width: 100%`, no fixed width, existing tokens only. Page: `PageHeader` `actions` = filled primary "Create team" `Button`; default-teams section kept, tightened; table name column shows the name and one truncated description line; an "Edit" `IconButton` (`size="medium"`, `color="on-surface-retreat"`, aria-label with the team name) in a trailing column, rendered only when `canAdmin`. Hooks from `controlPlaneApiEnhancements.ts` only, regenerated client; the edit mutation invalidates the registry list tag.

## Risks / Trade-offs

- [A platform admin can make themselves admin of any team, then editor, and read its content] → platform admin only, audited per save; agreed by the owner and the team (decision 1).
- [Pending nominee cannot replace the sole admin in one step] → explicit 409 message; consistent with `_ensure_team_keeps_at_least_one_admin`.
- [Relation writes and metadata write are not one transaction] → pre-check before writes, residual race documented (D5).
- [FGA model change] → `schema.fga.json` regenerated; if a deployment pins `authorization_model_id`, operators must point it at the new model.

## Migration Plan

Merged into #3067's note (`3067-require-team-description.md`, already `impact: minor`). The model is written at startup by default (`sync_schema_on_init: true`); a deployment pinning `authorization_model_id` with sync disabled publishes the new model first. No database migration. Rollback: redeploy the previous release; the extra FGA permission is unused by older code.

## Implementation notes

- An unchanged description is dropped from the patch, and an edit that changes nothing writes no audit event.
- A default (placeholder) description opens empty in the dialog and may stay empty, as in team settings (#3067).
- The admins label becomes "Team admin(s)" for both modes ("Initial" read wrong in edit).
