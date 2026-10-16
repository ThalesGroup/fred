## 0. Preconditions

- [ ] 0.1 Owner answers the open questions in proposal.md (question 1 needs reviewer agreement); update specs/design if an answer differs from the recommendation
- [ ] 0.2 PR #3071 is merged; rebase this branch on `origin/swift` and verify `TeamDescription` and `@core/utils/teamFields.ts` exist

## 1. Authorization model

- [ ] 1.1 Add `define can_edit_team_registry: platform_admin` to `organization` in `schema.fga`, regenerate `schema.fga.json`, add `OrganizationPermission.CAN_EDIT_TEAM_REGISTRY`; confirm how the model reaches OpenFGA (startup write vs pinned `authorization_model_id`) and record it for the migration note; verify `test_rebac_schema_authz05.py` covers platform_admin allowed, team_manager denied

## 2. Backend

- [ ] 2.1 Extract the rename/description write of `update_team` into a shared helper; verify existing `update_team` rename and description tests still pass unchanged
- [ ] 2.2 Add `EditTeamRegistryRequest` (name, description, add_admin_ids, remove_admin_ids; overlap refused) and verify schema unit tests for 422 cases
- [ ] 2.3 Add the service function (permission check, lock, admin diff with charter resolution, last-admin guard, metadata write, cache invalidation, audit event) and verify tests: edit all three, 403 team_manager, 404 personal space, 409 name taken, 409 last admin, removed admin stays member, pending nominee, audit emitted once and not on refusal
- [ ] 2.4 Add `PATCH /teams/{team_id}/registry` in `teams/api.py`, regenerate `openapi.json` (`make generate-openapi`), verify a route test returns 200 with the updated `TeamWithPermissions`
- [ ] 2.5 Add the route to `validation/scenarios/test_team_registry_authz.py` (platform_admin allowed, team_manager denied)

## 3. Generated client

- [ ] 3.1 `cd apps/frontend && make update-control-plane-api`; export a friendly hook alias from `controlPlaneApiEnhancements.ts` with registry-list invalidation; verify `tsc` passes and no type is hand-declared

## 4. Frontend

- [ ] 4.1 Create `TeamFormDialog` (create and edit modes) on the `Dialog` molecule with name, description and admins fields; verify tests: confirm disabled while invalid, create payload, edit sends only changed fields and the admin diff
- [ ] 4.2 Condense `AdminTeamsPage`: header "Create team" button, inline create section removed, description line under the name, "Edit" IconButton for platform admins only; verify `AdminTeamsPage.test.tsx` for both roles
- [ ] 4.3 Add fr and en keys for every new string; verify no key is missing in either locale
- [ ] 4.4 Verify styles use existing tokens only and dialog content is `width: 100%`

## 5. Docs and close-out

- [ ] 5.1 Add a dated entry to `CONTROL-PLANE-PRODUCT-CONTRACT.md` and update REBAC.md "Team registry governance" and "Delegated admin roles"
- [ ] 5.2 Add the migration note under `docs/swift/ops/migrations/` and verify `make migration-check`
- [ ] 5.3 Run `make code-quality`, `make test` (control-plane, fred-core, frontend), `ruff --select I` and basedpyright; record results here
- [ ] 5.4 Manual check by the owner: create a team, edit name, description and admins, try removing the last admin
