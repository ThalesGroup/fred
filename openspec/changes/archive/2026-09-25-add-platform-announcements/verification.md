# Verification — add-platform-announcements

Branch `feat/platform-announcements`, five commits off `swift`
(`9bd13ca04` … `33ff09d50`). Everything below was run locally on 2026-09-25
against the docker-compose stack.

## Commands and results

| Command | Where | Result |
| --- | --- | --- |
| `make code-quality` | monorepo root | exit 0 (ruff + format + pyright + bandit across all modules, tsc + prettier + eslint on the frontend) |
| `pytest -m "not integration" --disable-socket --allow-unix-socket` | `apps/control-plane-backend` | 1303 passed, 8 deselected |
| `npx vitest run` | `apps/frontend` | 2865 passed, 9 skipped, 245 files |
| `alembic heads` | `apps/control-plane-backend` | one head, `b88202b8451e` |
| `alembic upgrade head` → `downgrade -1` → `upgrade head` | same, against local Postgres | clean each way |
| `alembic check` | same | "No new upgrade operations detected" |
| `make check-config-files` | same | all four `config/*.yaml` valid against the regenerated schema |
| `make update-control-plane-api` | `apps/frontend` | regenerated `controlPlaneOpenApi.ts`; `info_banner` gone, six announcement hooks present |
| `fred-performance-reviewer` skill | full diff | no high-blast-radius finding; two frontend inefficiencies raised and fixed (below) |
| `/code-review high swift...HEAD` | full diff | four findings, all four addressed (below) |

## Tests added

- `apps/control-plane-backend/tests/test_announcement_store.py` — 9 tests: CRUD
  round-trips, `list_enabled` never leaking a disabled row, `set_enabled`
  leaving `content_version` untouched, unknown-id returns.
- `apps/control-plane-backend/tests/test_announcements.py` — 21 tests:
  `content_version` bumping (text and `dismissible` bump it; `enabled`, via
  either endpoint, does not), delivery filtering, `can_manage_platform` asked on
  all five admin operations and nothing written behind a refusal, audit events
  in order, 404s, and payload validation including the blank-locale cases.
  Plus two route-level tests: `/announcements/active` 401s without a bearer
  token, and every announcement route is present in the OpenAPI document.
- `apps/frontend/.../announcementDismissal.test.ts` — 9 tests: version-keyed
  dismissal, pruning to one entry per announcement, and every storage failure
  mode (corrupted value, non-array, throwing read, throwing write) degrading to
  "never dismissed".
- `apps/frontend/.../AnnouncementBanner.test.tsx` — 9 tests: conditional
  more-info and dismiss actions, the dialog not taking the banner with it,
  locale fallbacks, and the dismissal being reported only after the collapse.
- `apps/frontend/.../AnnouncementStack.test.tsx` — 8 tests: severity then age
  ordering, empty and undefined data, dismissal filtering, an edited
  announcement returning both across loads and in a tab that stayed open, and
  the cross-session refresh contract.
- `apps/frontend/.../AnnouncementsPage.test.tsx` — 7 tests: listing, the live
  count, severity marking, the toggle using the dedicated endpoint and never the
  content update, confirmed delete, and opening the editor.

`apps/control-plane-backend/tests/test_main.py` lost
`test_frontend_config_exposes_configured_info_banner` with the field it covered,
and its sibling assertion was rewritten to state why announcements are absent
from that surface.

## Findings addressed

**Performance pass.** No blocking I/O, no new engine or client (the store takes
the shared `get_pg_async_engine()`), and no new KPI needed — `KPIMiddleware`
already emits `api.request_latency_ms` for every route, so the polled endpoint
is Grafana-visible for free. Two real inefficiencies were fixed: `isDismissed`
was called once per announcement inside the render filter, each call parsing the
stored JSON (now one `readDismissedSet()` per render), and a poll returning
identical content still handed back a fresh array, re-running the markdown
pipeline for every banner once a minute in every open tab (banner now memoized).

**Independent code review** raised four, all fixed in `33ff09d50`:

1. The post-auth gate was inert. `useAuth().isAuthenticated` is
   `!!GetUserRoles()`, and that call always returns an array, so the flag is
   never false — banners would have rendered and polled on the GCU-acceptance
   and root-bootstrap screens, contradicting this change's own contract entry.
   The stack now renders inside `GcuGuard`/`BootstrapGuard`; `.appContent`
   became a flex column with a `.routedContent` child so the push-down layout is
   unchanged. The unit test had asserted against a mocked state production
   cannot produce, which is why it passed.
2. In-session dismissal state was keyed by id while stored dismissals are keyed
   `id@content_version`, so an announcement edited while a tab stayed open never
   came back until a reload.
3. Locale resolution stopped at `en`. A French-only announcement — ordinary,
   since the backend requires one locale and the editor opens on the French tab
   — rendered for an English viewer as an accented strip with an icon, a close
   button and no text. `resolveAnnouncementText` now falls back to any authored
   locale.
4. Stale docs: `info_banner` still documented as current in
   `CONTROL-PLANE-PRODUCT-CONTRACT.md` §3.1.1 and §42, and `InfoBanner` still
   named in `FRONTEND_CODING_GUIDELINES.md` §2.5. §42 is now marked superseded
   by §55, the field is gone from §3.1.1, and §2.5 points at `.routedContent`.

## Divergences from the plan

- **Task 3.2** planned RTK Query's `pollingInterval` + `refetchOnFocus` on the
  read query. `refetchOnFocus` is inert in this app — `setupListeners` is never
  called — so the stack reuses the existing `crossSessionRefresh` helper, which
  already exists for this exact problem and already uses a 60 s interval plus an
  explicit focus listener. Recorded in `design.md`.
- **Task 4.1** said "rework `InfoBanner`". In practice the component was
  replaced: `AnnouncementBanner` is a new molecule and the `InfoBanner`
  directory was deleted. Same outcome, cleaner name.
- `shared/utils/severity.ts` was added beyond the task list to hold the
  severity → icon map that `UploadWarningBanner` had privately, so the two
  surfaces cannot drift. The severity → accent colours stay per-stylesheet, as
  Toast and `UploadWarningBanner` already do — sharing those would mean touching
  two unrelated components.

## Not verified

- No run against a real multi-replica deployment. The endpoint is a single
  indexed `SELECT` on an unpartitioned table and the payload is small, so no
  load test was judged necessary; if the enabled set ever grows large, the
  polling cost is worth re-measuring.
- The banner stack has not been exercised by hand in a browser against the
  running stack — coverage is unit-level.
