## 0. Preconditions

- [x] 0.1 Owner answers recorded in proposal.md "Owner decisions" (2026-10-16), all as recommended; question 1 agreed at the daily meeting
- [x] 0.2 Bundled into PR #3071 instead of waiting for its merge (owner, 2026-10-16): #3071 rebased on `origin/swift`, `TeamDescription` and `@core/utils/teamFields.ts` present

## 1. Authorization model

- [x] 1.1 Add `define can_edit_team_registry: platform_admin` to `organization` in `schema.fga`, regenerate `schema.fga.json`, add `OrganizationPermission.CAN_EDIT_TEAM_REGISTRY`; confirm how the model reaches OpenFGA (startup write vs pinned `authorization_model_id`) and record it for the migration note; verify `test_rebac_schema_authz05.py` covers platform_admin allowed, team_manager denied

## 2. Backend

- [x] 2.1 Extract the rename/description write of `update_team` into a shared helper; verify existing `update_team` rename and description tests still pass unchanged
- [x] 2.2 Add `EditTeamRegistryRequest` (name, description, add_admin_ids, remove_admin_ids; overlap refused) and verify schema unit tests for 422 cases
- [x] 2.3 Add the service function (permission check, lock, admin diff with charter resolution, last-admin guard, metadata write, cache invalidation, audit event) and verify tests: edit all three, 403 team_manager, 404 personal space, 409 name taken, 409 last admin, removed admin stays member, pending nominee, audit emitted once and not on refusal
- [x] 2.4 Add `PATCH /teams/{team_id}/registry` in `teams/api.py`, regenerate `openapi.json` (`make generate-openapi`), verify a route test returns 200 with the updated `TeamWithPermissions`
- [x] 2.5 Add the route to `validation/scenarios/test_team_registry_authz.py` (platform_admin allowed, team_manager denied)

## 3. Generated client

- [x] 3.1 `cd apps/frontend && make update-control-plane-api`; export a friendly hook alias from `controlPlaneApiEnhancements.ts` with registry-list invalidation; verify `tsc` passes and no type is hand-declared

## 4. Frontend

- [x] 4.1 Create `TeamFormDialog` (create and edit modes) on the `Dialog` molecule with name, description and admins fields; verify tests: confirm disabled while invalid, create payload, edit sends only changed fields and the admin diff
- [x] 4.2 Condense `AdminTeamsPage`: header "Create team" button, inline create section removed, description line under the name, "Edit" IconButton for platform admins only; verify `AdminTeamsPage.test.tsx` for both roles
- [x] 4.3 Add fr and en keys for every new string; verify no key is missing in either locale
- [x] 4.4 Verify styles use existing tokens only and dialog content is `width: 100%`

## 5. Docs and close-out

- [x] 5.1 Add a dated entry to `CONTROL-PLANE-PRODUCT-CONTRACT.md` and update REBAC.md "Team registry governance" and "Delegated admin roles"
- [x] 5.2 Add the migration note under `docs/swift/ops/migrations/` and verify `make migration-check`
- [x] 5.3 Run `make code-quality`, `make test` (control-plane, fred-core, frontend), `ruff --select I` and basedpyright; record results here
- [x] 5.5 Owner UX fixes (2026-10-16): localized refusal toasts from a stable `code` on the three 409s; `Team.pending_admin_ids` and a pending marker in the table and dialog chips; "500 characters maximum" on the description field at its limit; `--spacing-s` between the admin search and its chips; contract §67 and COMPONENT-UX.md updated, client regenerated
- [x] 5.4 Manual check by the owner: create a team, edit name, description and admins, try removing the last admin (owner, 2026-10-16: satisfied)
- [x] 5.6 Owner UI polish (2026-10-16): page column 1080px like the other admin tables, `small` row switches, `dense` 560px dialog with `small` inputs, six-row description, Autocomplete menu portaled (fixed position, flips above under 240px, like `Select`) so the dialog body does not clip it, new optional `closeOnEscape` on `DialogPrimitive`/`Dialog` (default `true`) set to `false` on the team dialog
- [x] 5.7 Author and independent review fixes (2026-10-16, after rebase on `origin/swift` 762a401b2): migration re-parented on `d4e8b2a6f091` and rollback revision corrected; audit event kept when the edit fails after admin writes; `TextArea` ties error/hint to `aria-describedby` and sets `aria-invalid`; admin search `minQueryLength={2}` with localized messages and chip remove label; registry edit invalidates `PlatformAccess` and per-member tags; COMPONENT-UX and REBAC.md wording

## Verification (2026-10-16)

- Model: written at startup by default (`sync_schema_on_init: true`); a pinned `authorization_model_id` with sync off must publish the new model first (migration note). `test_rebac_schema_authz05.py` asserts `can_edit_team_registry` is `platform_admin` only; the integration closed-world check picks it up by enumeration.
- Backend: `tests/test_team_registry_edit.py` (16 tests: full edit + audit, removed admin keeps other roles, team manager 403, unknown/personal 404, name taken and rename race 409, last admin and pending-only replacement 409 with nothing written, charter-pending add, self-removal, no-op writes no audit, 4 invalid bodies 422, route 200/422). Existing `update_team` rename tests unchanged and green.
- `make code-quality` (root, all 17 modules): exit 0. `ruff check --select I` and basedpyright on touched control-plane files: clean.
- `make test`: control-plane-backend 1992 passed, 10 skipped; fred-core 1274 passed, 1 skipped; frontend 4361 passed, 6 failed (2 AgentFormModal files: missing Redux provider for `useTeamRoutingPolicyQuery`; fail identically on `origin/swift`, untouched here). `AdminTeamsPage.test.tsx` 19 passed.
- `make migration-check`: valid. `openspec validate platform-admin-team-edit --strict`: valid.
- Not run: the validation scenario (`validation/scenarios/test_team_registry_authz.py`, needs a live stack) and task 5.4 (owner manual check).
- Owner UX fixes (task 5.5): root `make code-quality` exit 0 (incl. basedpyright, `ruff --select I` clean on touched files); control-plane `make test` 1994 passed, 10 skipped (new: stable refusal codes on the route, pending admins in the bulk listing); frontend vitest on `AdminTeamsPage`, `TeamSettingsPanel`, `core/errors`, `core/hooks`: 315 passed (new: localized refusal toasts per code and generic fallback, pending marker in row and chip, 500-character message in dialog and settings, chips in their own spaced row).
- Final, after rebase on `origin/swift` 762a401b2 (2026-10-16): migration `c9acb7dd3ad0` re-parented on `d4e8b2a6f091`; `alembic heads` single head; `db-check-sqlite` and `db-check-postgres-full` (upgrade, `alembic check`, downgrade base) passed. `make code-quality` per Python module (control-plane, fred-core, knowledge-flow): exit 0, basedpyright 0 errors. Frontend (direct `npx`, not the make targets, a Vite was running): `tsc` clean, prettier clean, eslint clean. Control-plane `make test` 2007 passed, 10 skipped, then `test_team_registry_edit.py` 19 passed after the audit fix; fred-core `make test` 1274 passed, 1 skipped. Vitest on touched areas (Autocomplete, Dialog, TextArea, admin pages, TeamSettingsPanel, AddPeopleDialog, TeamCard, TeamDescriptionReminder, marketplace, TeamAgentsPage, ServiceNotice, core, controlPlane slice): 1136 passed, 6 failed, the same pre-existing `AgentFormModal` provider failures as on `origin/swift`. `make migration-check` on the committed branch: valid. Owner manual check (5.4): done 2026-10-16.
- Known limitations kept: the portaled menu caps its height at the list's own maximum, not the space left in the viewport (same as `Select`); the scrim still closes the team dialog; on a team with no active admin, the registry edit refuses a pending-only nominee, so `rescue-admin` stays needed there.
