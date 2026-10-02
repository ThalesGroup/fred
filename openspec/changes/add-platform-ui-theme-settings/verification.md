# Verification: add-platform-ui-theme-settings

Commits on `ui-theme-polish`: `020ed8fec` (control plane), `29d727d10` (frontend), `ece833b98`
(docs), plus the review follow-up commit that adds this file.

## Control plane

- `tests/test_platform_ui_settings.py` (16 tests): store empty until saved, round trip and overwrite
  of the single row, re-saving identical values still records the save; request validation rejects
  a hidden default, repeated ids, a non-matching id, a 33-character id, 33 hidden ids and extra
  fields, and accepts ids the backend does not know; a user without `can_manage_platform` can
  neither read nor write (no store write); a platform admin reads defaults then writes; public
  `GET /frontend/config` (unauthenticated) omits `ui_themes` when never saved, omits a null
  `default_theme`, exposes saved settings, and stays 200 without `ui_themes` when the settings store
  fails (unmigrated database).
- `make code-quality` (ruff, bandit, basedpyright): clean. `make test`: 1457 passed (before the
  review follow-up); `tests/test_main.py` + `tests/test_authz_endpoint_matrix.py` after it: 186
  passed.
- Alembic: one head (`c4d7e2a91b30`); `alembic upgrade head`, `downgrade -1`, `upgrade head` run on
  the local Postgres database.
- `controlPlaneOpenApi.ts` regenerated with `make generate-openapi` (control plane) and
  `npx --no-install @rtk-query/codegen-openapi src/slices/controlPlane/controlPlaneOpenApiConfig.json`
  (frontend). The frontend `make update-control-plane-api` target was not used: its `node_modules`
  prerequisite would have run `npm ci` under the running dev server.

## Frontend

- `src/app/uiThemes.test.ts`: `resolveUiTheme` / `offeredUiThemes` rules (choice offered, hidden
  choice, default unset / hidden / unknown, everything hidden); `theme-boot.js` run in `node:vm`
  agrees with them on a case table including platform settings and malformed caches.
- `src/app/platformTheme.e2e.test.tsx`: with platform settings `{cobalt, hidden pebble}`,
  `applyResolvedTheme` (what `index.tsx` applies before render) and the provider resolve the same
  theme for no choice, a hidden choice and an offered choice, and never rewrite the stored choice;
  the platform cache is written and removed.
- `UiSettingsPage.test.tsx` (6 tests): stored settings shown, Save disabled until a change, blocked
  when the default is hidden or nothing is offered, saves `default_theme: null` for "none", keeps
  unknown ids, shows a load error instead of defaults.
- `UserSettingsPage.test.tsx`: the picker lists offered themes only and is hidden with one theme
  while the mode choice stays.
- `npx tsc --noEmit`, prettier, eslint (src + public): clean. Whole `npx vitest run`: 3199 passed,
  7 skipped, 4 failed in `src/rework/core/hooks/useChatSse.test.tsx`, unrelated and already failing
  on `swift`.
- Help Center tests: 17 passed.

## End to end (task 3.3)

The control-plane API was restarted on the new code. A temporary row (default `cobalt`, `pebble`
hidden) was written to the local database, then deleted. Headless Chromium against the dev server,
Keycloak stubbed, tracing every `data-ui-theme` / `data-theme` change on `<html>`:

| Case | Boot script | After `/frontend/config`, before render |
| --- | --- | --- |
| New user, no cache | pebble / light | cobalt / light |
| Returning user, cache | cobalt / light | cobalt / light |
| Stored pebble (hidden) | cobalt / light | cobalt / light |
| Stored cloud, dark | cloud / dark | cloud / dark |

The only change happens for a first visit without cache, before any application content exists,
which the spec allows. The admin page itself was not exercised in a signed-in browser (no test
credentials); its behavior is covered by the component tests above.

## Reviews

Independent agents reviewed the backend step (stale Alembic parent, server default, two missing
test cases: fixed or planned), the frontend step (hand-copied generated type, dead constant,
missing agreement tests, no load-error state: fixed) and the whole change (unmigrated database
taking the login page down, field description, Help Center gaps, unknown default in the dropdown,
task wording: fixed).

## Not done

- Task 4.4: re-parent `c4d7e2a91b30` onto the current `swift` Alembic head after rebasing
  (`origin/swift` already has `d7822fba0d40` on the same parent).
- A signed-in manual pass on the admin page and the profile picker.
