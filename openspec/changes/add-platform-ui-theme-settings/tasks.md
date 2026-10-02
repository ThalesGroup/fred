## 1. Control plane storage and API

- [x] 1.1 Add the `platform_ui_settings` model (singleton CHECK, `default_theme`, `hidden_themes`, `updated_by`, `updated_at`), register it in `table_ownership.py` and add the Alembic migration on the current head; verify `alembic heads` shows one head and `alembic upgrade head` succeeds on a local database
- [x] 1.2 Add `platform_ui_settings/` store and service (get, replace, validation: id format, max 32 ids, distinct, default not hidden) guarded by `CAN_MANAGE_PLATFORM`; verify unit tests cover each validation error and the 403 path
- [x] 1.3 Add `GET` / `PUT /control-plane/v1/admin/platform/ui-settings`, mount the router, add the endpoints to `docs/swift/platform/authz-endpoint-matrix.yaml` (checked by `test_authz_endpoint_matrix.py`); verify API tests pass
- [x] 1.4 Add `ui_themes` to `FrontendConfig` and `build_frontend_config` (`None` without a row); verify a test of `GET /frontend/config` with and without settings, unauthenticated
- [x] 1.5 Regenerate the OpenAPI spec and `controlPlaneOpenApi.ts` (`make update-control-plane-api`); verify `make code-quality` and `make test` in `apps/control-plane-backend` pass

## 2. Frontend resolution

- [x] 2.1 Add `resolveUiTheme` with the spec's rules and a case-table test (offered set, stored hidden, default hidden or unknown, nothing offered)
- [x] 2.2 Cache `ui_themes` from `/frontend/config` in localStorage, apply the boot-script copy of the rules to it, and re-resolve in `index.tsx` after `loadConfig()` before render; verify the boot script passes the same case table
- [x] 2.3 Make `ApplicationContextProvider` expose the offered themes and resolve with `resolveUiTheme`; verify the `src/app` tests pass

## 3. Admin page and profile

- [x] 3.1 Add the "Interface utilisateur" admin page, nav entry and protected route (fr/en strings), using the generated hooks; verify a test covers loading, saving and the two blocking states
- [x] 3.2 Make the profile picker list offered themes only and hide it when one is offered; verify a test for the single-theme case
- [x] 3.3 Manual check: set default Cobalt and hide Pebble as admin, open a private window as a new user and confirm the first painted screen is Cobalt with no theme switch

## 4. Docs and close-out

- [x] 4.1 Add the dated `FrontendConfig.ui_themes` and admin endpoints entry to `CONTROL-PLANE-PRODUCT-CONTRACT.md`, update the theme section of `FRONTEND_CODING_GUIDELINES.md`
- [x] 4.2 Add the Help Center fr/en page for the admin setting and the migration note; verify `make migration-check` passes
- [x] 4.3 Run `/code-review` on the diff, then record frontend and control-plane verification evidence in `verification.md`
- [x] 4.4 Before merge, after rebasing on `swift`: re-parent `c4d7e2a91b30` on the current `swift` Alembic head (`down_revision` and `Revises:`); verify `alembic heads` shows one head and `alembic upgrade head` succeeds
