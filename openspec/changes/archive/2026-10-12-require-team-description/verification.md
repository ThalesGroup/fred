# Verification - require-team-description

Run on 2026-10-12, branch `feat/team-description-required`, Alembic revision
`c9acb7dd3ad0` (parent `93427a5fe874`).

## Proven

| Check | Command (from the project root named) | Result |
| --- | --- | --- |
| fred-core tests | `libs/fred-core`: `pytest -q -m "not integration" --disable-socket --allow-unix-socket` | 1278 passed, 1 skipped |
| fred-core lint | `ruff check .` and `ruff format --check .` | clean |
| Control-plane tests | `apps/control-plane-backend`: same pytest command | 1801 passed, 9 skipped |
| Control-plane lint | `ruff check .` and `ruff format --check .` | clean |
| Knowledge Flow tests | `apps/knowledge-flow-backend`: same pytest command | 1445 passed, 45 deselected |
| Knowledge Flow lint | `apps/knowledge-flow-backend`: `ruff check .` and `ruff format --check .` | clean |
| Single Alembic head | `alembic heads` | `c9acb7dd3ad0 (head)` only |
| Migration on SQLite | throwaway file: upgrade to `93427a5fe874`, seed NULL / blank / "Ops" / padded / long rows, `upgrade head`, `alembic check`, `downgrade -1`, `upgrade head`, `downgrade base` | backfill, trim, CHECK, 180-character cut and NULL restore as specified; `alembic check`: no new operations |
| Migration on PostgreSQL | dev database: `alembic upgrade head` | applied; column `VARCHAR(500) NOT NULL`, constraint present, 4 of 5 teams carry the placeholder |
| Migration round trip on PostgreSQL | throwaway database (`DATABASE_URL`), dropped afterwards: upgrade to `93427a5fe874`, seed NULL / blank / "Ops" / padded / 180-character rows, `upgrade head`, three invalid inserts, add a 300-character row, `downgrade -1`, `upgrade head` | NULL, blank and "Ops" become the placeholder, the padded row is trimmed; NULL, "Short" and 501 characters are refused (NOT NULL, `ck_teammetadata_description_min_length`, `VARCHAR(500)`); downgrade restores nullable `VARCHAR(180)`, placeholders become NULL, 300 characters cut to 180; second upgrade ends on `c9acb7dd3ad0 (head)` |
| Frontend types | `apps/frontend`: `npx tsc --noEmit -p .` | clean |
| Frontend lint | `npx eslint` and `npx prettier --check` on the changed files | clean |
| Frontend tests | `npx vitest run` | 331 files passed, 3983 tests passed, 7 skipped |
| Owner check in the app | create, edit, reminder, marketplace cards | confirmed by the owner, 2026-10-12 |
| OpenSpec | `openspec validate require-team-description --strict` | valid |
| Migration note | `scripts/migration_guides.py check-pr --base origin/swift --worktree` | 1 new declaration, valid |

Scenario coverage:

- Creation and edit bounds, 422 before the service, trimmed storage, placeholder
  flag, import fallback and migration: `apps/control-plane-backend/tests/test_team_description.py`.
- Helper, patch rule and database refusal: `libs/fred-core/fred_core/tests/teams/test_team_description.py`.
- Teams created from the user list and the import warning: `tests/test_import_export_users.py`.
- Personal space without description or placeholder: `tests/test_main.py`.
- Storage backfill creating a team record:
  `apps/knowledge-flow-backend/tests/features/test_storage_backfill_untagged.py`.
- Create form, settings field, reminder, cards: `AdminTeamsPage.test.tsx`,
  `TeamSettingsParameters.test.tsx`, `TeamDescriptionReminder.test.tsx`,
  `TeamCard.test.tsx`, `MarketplaceTeams.test.tsx`.

## Not proven

- **`make db-check-postgres-full`.** It starts a Docker Compose PostgreSQL; the
  PostgreSQL evidence is the dev database upgrade and the throwaway-database
  round trip above.
- **`alembic check` on the dev PostgreSQL** reports one difference, a column
  comment on `prompt.command`; it predates this change and does not concern
  `teammetadata`.
- **`validation/scenarios/test_team_registry_authz.py`.** Needs a live stack;
  its payloads were updated and linted only.
- **Root `make code-quality` and the frontend make targets.** Not run (they
  wipe a running Vite cache); the same tools were run directly.

## Divergences from design.md

1. **Import warning in English only.** Report warnings are server-side strings
   shown as they are; none is translated. The warning reads "N teams received a
   default description." ("1 team received a default description." for one). The French wording has
   no place to live without translating import warnings.
2. **Downgrade order.** The CHECK is dropped and the column made nullable
   before placeholders are cleared and long values cut, then the column is
   narrowed: clearing first would violate `NOT NULL`. Same end state.
3. **`reject_null_description` helper.** The "never cleared" rule is one
   fred-core function called from the validator of `TeamMetadataPatch` and of
   `UpdateTeamRequest`, rather than two copies.
4. **`TeamDescriptionReminder` organism.** The reminder used on the team home
   and in team settings is one small component wrapping `ServiceNotice`, so
   both places share the condition and it can be tested alone. On the team home
   it carries a filled `info` button to the team settings inside the notice.
5. **Settings field starts empty for a placeholder team** (owner decision,
   2026-10-12, after the independent review): the default text is not shown as
   a value, so a leftover of it can never be saved as a real description.
   Leaving the field empty sends nothing, shows the minimum-length error on
   the field, and the team keeps its default text.
6. **TeamCard renders no description block for a personal space**, which has
   none.
7. **Imported rows already carrying the placeholder count in the warning**: the
   team still has a description to write.
