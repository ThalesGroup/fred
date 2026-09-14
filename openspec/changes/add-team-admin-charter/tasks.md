## 1. Legal markdown loading and charter document

- [x] 1.1 Extract `useLegalMarkdown(name)` from `GcuPage` and `GdprPage` (same `contrib/<brand>/<name>.<lang>.md` → `<name>.md` order, same `<!doctype` rejection) and switch both pages to it, in its own `refactor:` commit; verify with a new hook test covering candidate order, brand and SPA-fallback rejection
- [x] 1.2 Add generic templates `apps/frontend/public/team-admin-charter.md` and `team-admin-charter.fr.md` (no deployment wording); verify the hook test resolves `team-admin-charter.fr.md` for a French language
- [x] 1.3 List `team-admin-charter` in `build-theme-archive.sh` (usage text and the missing-`.fr` warning loop) and in the theme archive tree of `apps/frontend/README.md`; verify by running the script on a directory holding only `team-admin-charter.md` and seeing the warning

## 2. Acceptance storage

- [x] 2.1 Add `team_admin_charter_version: str | None = None` to `AppConfig` next to `gcu_version`; verify the configuration files still load in `make test`
- [x] 2.2 Add `TeamAdminCharterAcceptanceRow` (`team_admin_charter_acceptances`, primary key `user_id` + `version`, `accepted_at` with `utcnow`) and register it in `models/table_ownership.py`; verify the table-ownership test passes
- [x] 2.3 Add the Alembic migration parented on the current control-plane head (`d3f8a2c6e174` today, re-parent if #2649 lands first); verify `alembic heads` shows one head and `alembic upgrade head` runs on the local Postgres
- [x] 2.4 Add the store (`get_acceptance(user_id, version)`, `accept(user_id, version) -> inserted: bool` with insert-if-absent) and expose it as `TeamServiceDependencies.get_team_admin_charter_store`; verify store tests for first insert, repeated insert keeping the first time, and two versions for one user

## 3. Permission gate

- [x] 3.1 Define `ADMIN_ONLY_TEAM_PERMISSIONS` and `TeamAdminCharterNotAcceptedError` (403, detail `team_admin_charter_not_accepted`), and apply the gate after the ReBAC check in `_validate_team_and_check_permission`; verify tests: unaccepted admin gets 403 on `update_team` and `add_team_member` with no relation written, accepted admin succeeds, older accepted version gets 403, unset version succeeds, non-admin keeps the plain ReBAC 403 without a store read
- [x] 3.2 Drop the five permissions from `_get_team_permissions_for_user` when the BatchCheck returned any of them and the acceptance is missing; verify tests: `get_team_by_id` projection for an unaccepted admin keeps `can_read_members` and lacks the five, admin plus analyst keeps `can_run_evaluations`, editor-only user triggers no store read
- [x] 3.3 Add a test asserting `ADMIN_ONLY_TEAM_PERMISSIONS` equals the permissions defined as `team_admin` alone in `libs/fred-core/fred_core/security/rebac/schema.fga`; verify it fails when a `define can_x: team_admin` line is added locally
- [x] 3.4 Apply the same filter to the evaluation permissions shared with `team_analyst` and to the routing policy read, so an unaccepted admin keeps only their other roles' rights; verify tests: a pure admin loses evaluations, an analyst admin keeps them, the routing read is refused for a pure unaccepted admin

## 4. API and contract

- [x] 4.1 Add the `team_admin_charter` router with `GET` and `POST /control-plane/v1/team-admin-charter` returning `TeamAdminCharterStatus {required, accepted_at}`; `required` reads the acceptance first and only then runs one `lookup_user_resources` on `can_administer_admins`; `POST` returns 409 `team_admin_charter_disabled` when no version is set and emits `team_admin.charter.accepted` through `emit_audit_log` only on insert; verify API tests for each spec scenario of the status and acceptance requirements
- [x] 4.2 Add both routes to `docs/swift/platform/authz-endpoint-matrix.yaml`; verify `tests/test_authz_endpoint_matrix.py` passes
- [x] 4.3 Regenerate the client with `cd apps/frontend && make update-control-plane-api`; verify the `controlPlaneOpenApi.ts` diff only adds the two endpoints and `TeamAdminCharterStatus`
- [x] 4.4 Add friendly hook aliases in `controlPlaneApiEnhancements.ts`, the status query providing a `ControlPlaneUser` tag and the mutation invalidating it plus `ControlPlaneTeam`; verify with `tsc`

## 5. Frontend

- [x] 5.1 Add `TeamAdminCharterContent` (charter through `useLegalMarkdown`, 1px end sentinel with `threshold: 0`, `onEndReached` callback); verify a component test where the callback fires once the sentinel intersects
- [x] 5.2 Add `TeamAdminCharterPrompt` mounted in `MainLayout`, shown only on the pages of a team the user administers, using the shared `Dialog` (Accept disabled until end reached, Later in component state only); verify tests: pending admin on their team opens the dialog, home page and non-administered team show nothing, Later closes it without calling the mutation, Accept calls it
- [x] 5.3 Add the `responsibilities` section to `TeamSettingsPage` and its entry in the `TeamContentNavbar` settings menu, both gated on `my_relations` including `team_admin`, showing the acceptance time or an Accept action; add the pending notice at the top of team settings linking to it; verify tests: admin sees the section, plain member is redirected to Members, pending admin sees the notice
- [x] 5.4 Add the en and fr i18n keys for the pop-up, the section and the notice; verify `tsc` and the frontend tests pass with no missing key warnings

## 6. Docs and handoff

- [x] 6.1 Add a dated contract section to `CONTROL-PLANE-PRODUCT-CONTRACT.md` (endpoints, 403 detail, gated permissions), a paragraph in the team admin section of `REBAC.md` (gate, the two functions, the routing read exception), and a charter section in `TERMS_OF_USE.md` (setting, theme files, rollout order); verify relative links resolve
- [x] 6.2 Run `make code-quality` and `make test` in `apps/control-plane-backend` and `apps/frontend`, the `fred-performance-reviewer` skill on the gate, and `/code-review` on the diff; verify all green and findings addressed
- [ ] 6.3 Open a draft PR against `swift` linking #2658; after merge, `openspec archive add-team-admin-charter` and close #2658
