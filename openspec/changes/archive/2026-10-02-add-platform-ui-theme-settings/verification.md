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
- Alembic: `c4d7e2a91b30` re-parented on the `swift` head `d7822fba0d40` after the rebase (task
  4.4). `make db-check-heads`: single head; `make db-check-sqlite`: upgrade, check and downgrade to
  base pass. Local Postgres: downgraded off the old parent, then `alembic upgrade head` ran
  `21e235382895 -> d7822fba0d40 -> c4d7e2a91b30`.
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
- `UiSettingsPage.test.tsx` (8 tests, tile layout, saved on change): stored settings shown without
  saving, Pebble shown as default when nothing is saved, a switch or "Set as default" saves at once,
  a failed save returns to the stored values with an error, the default and the last offered theme
  cannot be withdrawn, a withdrawn theme cannot become the default, unknown ids are kept, a load
  error locks the tiles.
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

After the rebase on `swift`, a second independent review of the whole change found no high-severity
bug. Fixed: a failed save could revert the tiles to settings older than the server's while the
post-save refetch was in flight (tiles now locked while refetching, test added), and a missing table
logged a full traceback on every public `/frontend/config` call (now one warning per outage, test
added). Left as known limits: two first saves at the same instant on a fresh install can collide on
the single row (500, retry succeeds); a transient database error serves no settings for that load,
so the cached platform settings are dropped until the next good load. A performance pass found the
added per-load read acceptable (one async primary-key read, session released on error); no cache.
Full suites after the rebase: frontend `make code-quality` and `make test` (3252 passed, 7 skipped,
0 failed), control plane `make code-quality` and `make test` (1466 passed), `libs/frontend` `npm
test` (379 passed, 1 skipped), `make migration-check` valid.

## Not done

- A signed-in manual pass on the admin page and the profile picker.
