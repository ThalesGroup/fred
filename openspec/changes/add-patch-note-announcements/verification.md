## Verification evidence (to fill during implementation)

Branch `feat/announcement-patch-notes`. Record the base commit and the Alembic
revision after the last rebase.

| Area | Command | Result |
| --- | --- | --- |
| control-plane | `cd apps/control-plane-backend && make test` | 1592 passed, 11 deselected (group A, 2026-10-09) |
| control-plane | `make code-quality` | clean (ruff, format, bandit, detect-secrets, basedpyright 0 errors) |
| Alembic | `make db-check-heads` | single head `cb6f39c6d80c` (parent `aac66348e27b`) |
| Alembic | `make db-check-sqlite` | passed (upgrade, check, downgrade base) |
| Alembic | `make db-check-postgres-full` (throwaway Postgres) | passed; dev DB upgraded, `alembic current` = `cb6f39c6d80c (head)` |
| authz matrix | `uv run pytest tests/test_authz_endpoint_matrix.py` | 1 passed |
| API client | `make generate-openapi` + `npx --no-install @rtk-query/codegen-openapi src/slices/controlPlane/controlPlaneOpenApiConfig.json` | regenerated; `npx tsc --noEmit` clean after adding `kind: "banner"` to three existing test fixtures (`Announcement.kind` is required) |
| frontend | `npx tsc --noEmit`, `npx prettier --check src`, `npx eslint src` | clean (group B gate, then group C gate, 2026-10-09) |
| frontend | `npx vitest run src/rework` | 278 files passed, 1 skipped; 3230 tests passed, 7 skipped (group C gate) |
| frontend (group C) | `npx vitest run src/rework/features/announcements src/rework/features/helpCenter src/rework/components/shared/molecules/PatchNoteDialog src/rework/components/pages/admin/AnnouncementsPage` | 12 files, 86 tests passed (`PatchNoteGate.test.tsx` 9, `patchNoteSession.test.ts` 2, Help Center 17) |
| Help Center | `npx prettier --check` on the four edited pages | clean |
| dev server | `curl` on Vite (5173) for `App.tsx`, `PatchNoteGate.tsx`, `patchNoteSession.ts`, `PatchNoteDialog.module.css` | new identifiers served; CSS module served as `__vite__css` |
| frontend (group B) | `npx vitest run src/rework/components/pages/admin/AnnouncementsPage src/rework/components/shared/molecules/PatchNoteDialog src/rework/features/announcements` | 8 files, 58 tests passed |
| i18n | `rework.announcements` key sets identical in fr and en | identical after group B (`jq` paths diff empty) |
| docs | `make migration-check MIGRATION_BASE=origin/swift` (root) | `Migration notes valid: 1 new declaration(s)` |
| performance | `fred-performance-reviewer` on `GET /announcements/patch-note` | no finding: async end to end, one session, two dependent indexed lookups (partial unique index predicate, then dismissal PK), no KPI/log/in-memory state, read once per load |
| visual | long patch note, fr/en, light/dark; admin preview equals user dialog | not done: no browser session overnight (Keycloak sign-in). CSS and DOM reviewed, no fix needed; left to the product owner (see below) |

### What the tests prove

- Backend (group A): kind rules, single active patch note (service and partial
  index, 409 on a race), activation events in the same transaction, per-user
  dismissal, deletion cleanup, authorization of every new route.
- Admin page (group B): both create actions, patch-note row and its controls,
  editor payload and previews, preview records no dismissal, history card.
- User flow (group C, `PatchNoteGate.test.tsx`): opens at load when a note is
  delivered (one read, no polling options); stays closed when none is
  delivered (no active note, or dismissed server-side); a plain close calls
  nothing and does not reopen on rerender or remount in the same session;
  ticking the box calls the dismissal with the note id; a fresh
  `sessionStorage` reopens it; a new note id opens after an older one was
  dismissed; a failed dismissal keeps the session flag, shows the error toast
  and logs nothing; a throwing `sessionStorage` does not break opening or
  closing; the body follows the UI language with the `en` fallback.
- `patchNoteSession.test.ts`: round-trip of a closed id, and graceful
  degradation when `sessionStorage` throws.

### What is not proven

- Visual check (task 6.3), left to the product owner. Open the app with a long
  patch note (several `##` sections, enough to scroll) in fr and en, light and
  dark, and check:
  1. the "Ne plus afficher" row stays pinned right above the action bar while
     the body scrolls, with no gap below it and no double border with the
     action bar's own top divider;
  2. the row's `surface-floating` background fully hides the text scrolling
     behind it, and spans the dialog's full width (its negative margins cancel
     the `Dialog` body padding);
  3. with a short note the row sits flush at the end of the body;
  4. the first heading's `surface-container` band and the `h2` dividers read
     well in both themes;
  5. the admin Preview (list and editor) looks identical to the dialog users
     get at load.
  Fallback if the row looks detached: a `footerStart` slot on `Dialog` (D9).
- Behaviour across real browser sessions and devices is covered by unit tests
  only, not by an end-to-end run.

### Review fixes (2026-10-09)

| Area | Command | Result |
| --- | --- | --- |
| control-plane | `make code-quality` | clean (ruff, format, bandit, detect-secrets, basedpyright 0 errors) |
| control-plane | `make test` | 1598 passed, 11 deselected |
| control-plane | `pytest tests/test_announcements.py tests/test_announcement_store.py` | 69 passed |
| frontend | `npx tsc --noEmit`; `npx eslint` + `npx prettier --check` on changed files | clean |
| frontend | `npx vitest run src/rework` | 278 files passed, 1 skipped; 3239 tests passed, 7 skipped |
| frontend | `npx vitest run` on announcements, PatchNoteDialog, AnnouncementsPage | 10 files, 78 tests passed |
| OpenSpec | `openspec validate add-patch-note-announcements --strict` | valid |
| dev server | control-plane API restarted (port 8222, no Traceback); `curl` on Vite (5173) for the changed TSX and the fr locale | new identifiers served |

What the new tests prove:

- `PatchNoteDialog.test.tsx`: Escape with the box ticked reports `true`;
  unticked, `false`. `PatchNoteGate.test.tsx`: Escape with the box ticked
  calls the dismissal mutation.
- `patchNoteSession.test.ts` and `PatchNoteGate.test.tsx`: the flag survives a
  new tab of the same sign-in (cleared `sessionStorage`), is absent after a new
  login session (`sid` or `session_state`) and for another user; writing prunes
  only the same user's other sign-ins; without a login-session id it falls back
  to per-user `sessionStorage`; throwing `localStorage`/`sessionStorage` does
  not break anything.
- `test_toggle_between_read_and_write_survives_a_content_save`: a toggle
  landing between `update_announcement`'s read and its write stands.
  `test_update_overwrites_fields_and_writes_the_given_version`: `store.update`
  leaves `enabled` alone.
- `test_concurrent_enabled_patch_note_creation_returns_409`: creating an
  enabled patch note that races another activation returns 409 and persists
  nothing (auto-disable on create was already covered by
  `test_creating_an_enabled_patch_note_disables_the_previous_one`).
- `test_add_dismissal_for_a_deleted_note_raises` (SQLite with foreign keys on)
  and `test_dismissing_a_note_deleted_meanwhile_returns_404`: a foreign-key
  failure surfaces as 404 instead of being swallowed.
- `AnnouncementsPage.test.tsx`: the header count ignores an active patch note;
  a failed toggle no longer calls `refetch` (RTK Query invalidates the static
  `LIST` tag on a rejected mutation).

Not proven: the login-session id is read from the access token; that Keycloak
issues the same `sid` to a second tab of one SSO session is assumed from its
documented behaviour, not checked end to end.

### Product-owner follow-up (2026-10-09)

- `AnnouncementsPage.test.tsx` (20 tests): one create button; the chooser
  shows exactly two tiles with icon and description and no pressed state; each
  tile closes the chooser and opens its editor; Escape closes it with the first
  tile focused; the history panel starts collapsed, expands as a labelled
  region and collapses again.
- `npx vitest run` on the announcements page, `PatchNoteDialog`,
  `features/announcements`, `features/helpCenter`, `ImportPanel` and
  `TeamResourcesPage`: 49 files, 373 tests pass. `npx tsc --noEmit`, eslint and
  prettier on the changed files are clean; `openspec validate --strict` passes.
- `libs/frontend`: `npm run build:ui` and `tests/validate-ui-archive.test.mjs`
  (58 tests) pass with the extended `SelectableCard`.

Not proven: the panel and chooser were not looked at in a browser beyond the
Vite module check.

### History as a view (2026-10-09)

- `ActivationHistory.test.tsx` (7 tests): the five column headers; rows newest
  first with label (French-only label for an English viewer), type, action
  icon and label, locale date, actor name; a banner chip in its severity tone,
  neutral for a patch note and for a null severity; sort by date from the
  header; uid and unknown-actor fallbacks; empty and error states.
- `AnnouncementsPage.test.tsx` (19 tests): Announcements is the default view
  with the create button; History shows the table with the five columns and
  hides the list and the create button; switching back restores them.
- Backend: `test_announcements.py` (banner severity snapshotted, null for patch
  notes), `test_announcement_store.py` (round trip with and without severity),
  `test_patch_note_announcement_migration.py` (nullable column). `make
  code-quality` clean; `make test`: 1599 passed.
- Dev DB aligned by hand with `ALTER TABLE platform_announcement_activation_event
  ADD COLUMN severity VARCHAR(16)` plus the column comment (as role `fred`);
  `alembic current` stays `cb6f39c6d80c`. The column sits last in the dev table,
  before `actor_uid` in a fresh database; nothing depends on column order.
- `git diff origin/swift` on `ImportPanel/` and `TeamResourcesPage.module.css`
  is empty.

Not proven: the table density and chip colours were checked in Vite by the
product owner only, not in a browser by the author.

### Patch-note title, dialog width, placeholder (2026-10-09)

- Backend `test_announcements.py`: a patch note keeps its cleaned title, is
  rejected with a blank or over-long title, normalizes severity, dismissible
  and short description; `label_for` falls back to the headline per locale for
  an untitled row; the history label is the title. `make code-quality` clean;
  `make test`: 1602 passed.
- Frontend: `npx vitest run` on the announcements page, `PatchNoteDialog`,
  `PromptEditor`, `features/announcements` and `features/helpCenter`: 13 files,
  127 tests pass. `npx tsc --noEmit`, eslint and prettier on the changed files
  clean; fr/en `rework.announcements` key sets identical.
- `git diff swift -- apps/frontend/src/rework/components/shared/molecules/PromptEditor/`
  is empty; the CSS custom-property check on the branch diff prints nothing.
- Control-plane client regenerated (`make generate-openapi`, then
  `npx --no-install @rtk-query/codegen-openapi src/slices/controlPlane/controlPlaneOpenApiConfig.json`):
  only two field descriptions changed.

Not proven: the dialog header and the editor title field were checked through
the Vite module only, not in a browser by the author.

### Dialog opens at the top (2026-10-09)

- Root cause reproduced in a test: before the change the opening focus landed
  on the checkbox inside the scrolling body (`opens with focus outside the
  scrolling body` fails on the previous commit's layout).
- `Dialog.test.tsx` `renders actionsAddon in the action bar, before the
  buttons`; `PatchNoteDialog.test.tsx` checkbox-in-action-bar and
  opening-focus tests pass. `npx vitest run` on `Dialog`, the announcements
  page, `PatchNoteDialog` and `features/announcements`: 11 files, 112 tests
  pass; `npx tsc --noEmit`, eslint and prettier clean.

Not proven: the scroll position itself (happy-dom has no layout) and the
action-bar look, which were not checked in a browser by the author.

### Dialog dividers (2026-10-09)

- `Dialog.test.tsx` `adds dividers only when asked` and `PatchNoteDialog.test.tsx`
  `rules off its header and action bar` pass; the same four suites: 11 files,
  114 tests pass; `npx tsc --noEmit` and eslint clean. Border colours checked
  through the Vite module only, not in a browser by the author.

### Review round (2026-10-09)

- Backend (`apps/control-plane-backend`): `make code-quality` clean (ruff,
  format, bandit, basedpyright 0 errors); `make test` 1607 passed,
  11 deselected; `make db-check-sqlite` passed; announcement suites alone
  (`test_announcements.py`, `test_announcement_store.py`,
  `test_patch_note_announcement_migration.py`) 80 passed;
  `tests/test_authz_endpoint_matrix.py` passed.
- Dev Postgres: downgraded `cb6f39c6d80c` -> `aac66348e27b` (old shape, with
  patch notes deleted first: 1 patch note, 1 dismissal, 8 history events
  lost), upgraded to the new `cb6f39c6d80c`, then round-tripped the new
  downgrade/upgrade once more; `alembic current` = `cb6f39c6d80c (head)`.
- Client regenerated (`make generate-openapi`, then
  `npx --no-install @rtk-query/codegen-openapi src/slices/controlPlane/controlPlaneOpenApiConfig.json`):
  `AdminAnnouncement`, `ActivePatchNote.dismissed`, field descriptions.
- Frontend (`apps/frontend`): `npx tsc --noEmit`, eslint and prettier clean on
  the changed folders; `npx vitest run` on the announcements page,
  `PatchNoteDialog`, `Dialog`, `MarkdownRenderer`, `FilterChips`,
  `UserProfile`, `features/announcements` and `features/helpCenter`:
  16 files, 184 tests passed. fr/en key sets under `rework.announcements` and
  `rework.profileMenu` identical. CSS custom-property check on the branch diff
  prints nothing. The running Vite serves the new modules (checked with curl).
- `make migration-check` and `openspec validate add-patch-note-announcements --strict` pass.

Not proven: the `FOR UPDATE` lock itself (SQLite ignores it; the test checks
that the three transactions ask for it), and the dialog's scroll position and
the new controls' look, which were not checked in a browser by the author
(happy-dom has no layout).

### Any re-enable re-shows the patch note (2026-10-09)

- Backend: `make code-quality` clean; `make test` 1606 passed, 11 deselected;
  announcement suites plus `tests/test_authz_endpoint_matrix.py` 80 passed;
  `make db-check-sqlite` passed. `test_re_enabling_a_patch_note_shows_it_again`
  (no edit: dismissed user sees it again, a new dismissal holds),
  `test_re_enabling_a_patch_note_edited_while_off_shows_it_again` and
  `test_editing_a_dismissed_patch_note_does_not_redeliver_it` pass.
- Dev Postgres: `ALTER TABLE platform_announcement DROP COLUMN
  edited_while_inactive` (no downgrade, patch notes kept); revision stays
  `cb6f39c6d80c`. `alembic check` against it reports no `platform_announcement`
  difference (only an unrelated `prompt.command` comment drift).
- Client regenerated: only the `content_version` description changed.
- Frontend: `npx vitest run src/rework/features/helpCenter
  src/rework/features/announcements` 6 files, 57 tests passed; prettier clean.
- `make migration-check` and `openspec validate add-patch-note-announcements --strict` pass.

### Re-enabling clears dismissals (2026-10-09)

- Backend: `make code-quality` clean; `make test` 1608 passed, 11 deselected.
  `test_re_enabling_clears_only_that_notes_dismissals` (both users' rows for
  the re-enabled note gone, the other note's row kept),
  `test_re_enabling_a_live_patch_note_keeps_its_dismissals`,
  `test_admin_list_counts_dismissals_since_last_enabled` (2, then 0),
  `test_re_enabling_a_patch_note_shows_it_again`,
  `test_editing_a_dismissed_patch_note_does_not_redeliver_it`, the store tests
  (`test_count_dismissals_per_note`, `test_delete_dismissals_spares_other_notes`)
  and the migration test (dismissal columns are exactly `announcement_id`,
  `user_id`, `dismissed_at`) pass.
- Dev Postgres (no downgrade): stale dismissals deleted first (0 rows), then
  `ALTER TABLE platform_announcement_dismissal DROP COLUMN content_version`;
  `\d` confirms the three columns. Control-plane API restarted, healthz 200.
- Client regenerated: field descriptions only.
- Frontend: `npx tsc --noEmit`, eslint and prettier clean; `npx vitest run
  src/rework/components/pages/admin/AnnouncementsPage
  src/rework/features/announcements` 102 passed, including the three
  pending-switch tests (toggle in flight, confirmation open, save and activate).
- `make migration-check` and `openspec validate add-patch-note-announcements --strict` pass.

Not proven: the delete's atomicity with the enable on Postgres (it shares the
toggle's transaction and row lock; SQLite tests cover the outcome only).

### Browser visual check (2026-10-09)

- Product owner tested in the running app: dense admin table, user dialog, create chooser, patch-note editor, re-enable rule and history pagination behave as specified (task 6.3).
