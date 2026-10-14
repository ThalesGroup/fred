# Verification

Evidence for `browse-patch-note-history` (issue #3080), branch
`feat/patch-notes-history`, as of 2026-10-13. Each line says what was run and
what it showed; "Not proven" at the end lists what nothing here establishes.

## Automated checks

Run after merging `origin/swift` into the branch (`ef696468c`), with each
project's own tools. The root `make code-quality` and the frontend `make test`
were deliberately not run: they wipe the cache of the Vite server the owner
was testing against. The frontend tools were run directly with `npx`.

| Project | Check | Result |
| --- | --- | --- |
| `apps/control-plane-backend` | pytest (offline suite) | 1799 passed, 9 skipped |
| `apps/control-plane-backend` | ruff check, ruff format, import order (`ruff --select I`), basedpyright | clean |
| `apps/frontend` | vitest (full suite) | 3982 passed, 7 skipped |
| `apps/frontend` | `tsc`, prettier | clean |
| `apps/frontend` | eslint, on the touched folders only | clean |
| `apps/frontend` | vitest on the `AnnouncementsPage` folder, after the last label change (`78d9eeefa`) | 84 passed |

The full frontend suite was not re-run after `78d9eeefa` (three files: the
two locale files and `PatchNoteAnnouncer.tsx`); only the folder run above was.

Re-run while writing this file:

- `openspec validate browse-patch-note-history`: valid.
- `alembic heads` in `apps/control-plane-backend`: one head, `a6c1d94e27b3`.

## Alembic

- One head, `a6c1d94e27b3`, on `e5ff6d80cc9f`, itself re-parented onto the
  `swift` head `9f6d3c2a1b08`; no merge revision.
- SQLite: `upgrade head`, `check` and the downgrade, plus the round trips and
  data conversions in `test_patch_note_announcement_migration.py` (position
  backfill, banner event pairing, lines without package, first package
  pending for nobody, seen column, downgrade/upgrade).
- PostgreSQL: both upgrades (`e5ff6d80cc9f`, then `a6c1d94e27b3`) ran clean on
  the developer's database, **before** `e5ff6d80cc9f` was re-parented onto
  `9f6d3c2a1b08`. The re-parenting changes the parent only, not the
  operations, but the re-parented chain itself was not replayed on
  PostgreSQL, and no downgrade was run on PostgreSQL.

## Owner's manual check

On the local stack, 2026-10-13. Reported by the owner as working ("tout
fonctionne bien"):

- announcing, and the frozen package in "What's new";
- the dialog not reopening after it was closed and the page reloaded;
- withdrawing the announcement;
- drag and drop, by mouse and by keyboard;
- the history, and reopening a package from it.

This is the owner's report, not a scripted run: the step list of task 9.2 was
written before the rework and was not followed item by item.

## Reviews

- Independent review (AGENTS.md, author review before readiness) and
  performance review: both done by reading the code (static). Their findings
  are fixed; see "Review Fixes" in design.md and section 11 of tasks.md.
- No load test was run.

## Spec scenarios against tests

The delta spec's scenarios were matched to tests by test name (backend:
`test_announcements.py`, `test_announcement_store.py`,
`test_patch_note_announcement_migration.py`; frontend: the
`AnnouncementsPage`, `PatchNoteDialog`, `UserProfile` and
`features/announcements` test files), not by re-reading each test body. Every
requirement has tests; these scenarios have only partial proof:

- "Two administrators announce at the same time": the tests check that the
  advisory lock is taken. SQLite takes no lock, so the exclusion itself is not
  exercised.
- "Reordering by drag and drop" and "Reordering with the keyboard": happy-dom
  has no layout, so the tests drive the drop through the drag-and-drop
  callbacks and check the sensors and the spoken texts. The real gestures
  rest on the owner's manual check.
- "Concurrent toggles write one change": covered by the row lock being
  requested, not by two concurrent transactions.
- The count in the announce label, "(X/10)": no test asserts it.

## Not proven

- The re-parented migration chain on PostgreSQL, and any downgrade on
  PostgreSQL.
- The guarded "seen" upsert and the advisory lock on PostgreSQL by an
  automated test: the offline suite runs on SQLite.
- Behaviour under load: no load test.
- `libs/frontend/tests/validate-ui-archive.test.mjs` was not run locally (it
  needs a full package build); CI runs it.
- The root `make code-quality` and the frontend `make test` as such, and any
  project other than the control-plane backend and the frontend.
- Anything in the running app beyond the five points of the owner's report,
  for example a second user's view or the upgrade of existing data.
