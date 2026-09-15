## 1. Legal markdown loading and charter document

- [x] 1.1 Extract `useLegalMarkdown(name)` from `GcuPage` and `GdprPage` in its own `refactor:` commit; verify with the hook test covering candidate order, brand and SPA-fallback rejection
- [x] 1.2 Add generic templates `apps/frontend/public/team-admin-charter.md` and `team-admin-charter.fr.md`; verify the hook test resolves `team-admin-charter.fr.md` for a French language
- [x] 1.3 List `team-admin-charter` in `build-theme-archive.sh` and the frontend README; verify the script warns when only `team-admin-charter.md` is present

## 2. Model and storage

- [x] 2.1 Add `pending_team_admin` to `schema.fga` (part of `team_member` only), recompile `schema.fga.json` with the OpenFGA CLI, add `RelationType.PENDING_TEAM_ADMIN` and let `lookup_resources` take a relation; verify the model test that `pending_team_admin` feeds `team_member` and nothing else
- [x] 2.2 Add `team_admin_charter_version` to `AppConfig`, the `team_admin_charter_acceptances` and `team_admin_charter_state` tables with their migrations, and register them in `table_ownership.py`; verify `alembic heads` shows one head
- [x] 2.3 Add the store (acceptance insert-if-absent, accepting user ids per version, applied version); verify the SQLite store test

## 3. Nomination, acceptance and reconciliation

- [x] 3.1 Resolve `team_admin` to `pending_team_admin` at every write (add member, grant role, rescue, team creation, import), refuse `pending_team_admin` in the request schemas, map its revoke to `can_administer_admins`, delete it on member removal and expose it in the member list; verify the nomination tests
- [x] 3.2 `POST /control-plane/v1/team-admin-charter` records the acceptance, audits the first one and promotes every pending team, and `GET` returns the caller's acceptance time or null; verify the acceptance and read tests and the 409 mapping
- [x] 3.3 Reconcile admin relations at startup when the configured version changed, fail-closed; verify the reconciliation tests for enabling, a new version, turning off and an unchanged version
- [x] 3.4 Remove the first version's permission gate and restore the routing policy and projection code to `swift`; verify the routing policy and projection tests pass unchanged
- [x] 3.5 Update `authz-endpoint-matrix.yaml` and regenerate `controlPlaneOpenApi.ts`; verify `test_authz_endpoint_matrix.py`

## 4. Frontend

- [x] 4.1 Add `TeamAdminCharterGate` around the `MainLayout` outlet and `TeamAdminCharterPage`; verify tests: a pending admin sees the charter on a team with no `team_admin` and a notice otherwise, admins, members and the home page see neither, Accept calls the mutation
- [x] 4.2 Open the Responsibilities section to `team_admin`s, with their acceptance time, and to pending admins, with Accept; verify the TeamSettingsPage and section tests
- [x] 4.3 Show "Admin (pending)" on the role chip, the team banner and the team lists, and gate its revoke on `canAdministerAdmins`; verify `tsc` and the affected tests
- [x] 4.4 Add the en and fr i18n keys and drop the first version's pop-up keys; verify `tsc`

## 5. Docs and handoff

- [x] 5.1 Rewrite `CONTROL-PLANE-PRODUCT-CONTRACT.md` §54, the `REBAC.md` paragraph and the `TERMS_OF_USE.md` section for the pending relation
- [ ] 5.2 Run `make code-quality` and `make test` in the touched modules, `/code-review` on the diff, rebase on `swift` and update draft PR #2669
- [ ] 5.3 After merge, `openspec archive add-team-admin-charter` and close #2658
