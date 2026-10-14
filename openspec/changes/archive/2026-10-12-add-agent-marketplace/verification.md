## Verification

Independent review of `feat/agent-marketplace` against `origin/swift` (merge base, no divergence on 2026-10-12), head `84ed68240` before this file. The reviewer was a separate agent and did not write the feature. It followed `AGENTS.md` "Author review before readiness". Frontend review was delegated read-only to a second fresh agent.

### Commands and results

| Check | Result |
| --- | --- |
| control-plane `make code-quality` | pass (ruff, format, basedpyright 0 errors) |
| control-plane `make test` | 1676 passed, 9 skipped, 11 deselected |
| `tests/test_agent_marketplace.py` | 33 passed |
| fred-sdk `make test` | 625 passed, 3 skipped |
| fred-runtime `make test` | 1914 passed, 11 skipped, 22 deselected |
| fred-core `make test` | 1260 passed, 1 skipped, 42 deselected |
| `alembic heads` | one head, `24c2f88374fe` |
| `alembic downgrade -2` then `upgrade head` on the dev Postgres | pass (both marketplace revisions round-trip) |
| `alembic check` | only the pre-existing `prompt.command` comment drift |
| frontend `npx tsc --noEmit -p tsconfig.json` | pass |
| frontend `npx vitest run` (full) | 318 files passed, 1 skipped; 3621 tests passed, 7 skipped |
| `scripts/migration_guides.py check-pr --base origin/swift --worktree` | valid, 1 declaration |

### What was reviewed

- Authorization on every new route: publish (`can_publish_marketplace_agents`, personal space 403), unpublish (team permission or platform admin, `reason` from platform admin only), dismiss (publishers and team admin), list, detail and like (any authenticated user, published entries only), import (`can_update_agents` per destination, publishing team refused, files from the snapshot through `asset_files`, never from the source team), admin settings (`can_manage_platform`). Entry lookups always filter on both agent and team, so there is no IDOR. The matrix entries match the code.
- The snapshot carries what a copy carries: capability configs go through the pod's `export-config` with scope-private settings reset.
- State machine, Modified derivation, auto-removal hooks (deactivate, suspend, delete cascade, private, switch off), quota, version and 409, likes per version with soft unlike, `<name> (<word> <n>)` naming, failed republication.
- Migrations: indexes, FK `CASCADE` / `SET NULL`, partial unique index with both `postgresql_where` and `sqlite_where`.
- Frontend: visibility per role, dialogs, i18n key parity fr/en, CSS tokens, `aria-pressed`, keyboard access to the Removed popover, generated hooks only.

### Fixed during review

- `ae92eab2a` **Important**: a publisher could publish a deactivated or suspended agent, which undid the automatic removal. Publish now answers 409 `marketplace_agent_inactive` (localized; contract and matrix updated; test added).
- `84ed68240` **Important**: on the admin Marketplaces page, moving a team back to Default when that turns its switch off sent `?agents_publisher_enabled=null`, and the impact endpoint answered 422, so the change was blocked. The parameter is now omitted (test added).

### Remaining findings (not fixed)

- **Owner decision, team deletion**: `delete_team` now deletes the team's agent instances, so entries, likes and imports cascade (task 3.10). This cannot be undone, and it emits no `agent.deleted_total` KPI, unlike `unenroll_agent_instance`. Other team data (prompts, resources) is still left in place by team deletion. The scope is correct: only rows with that `team_id` are deleted.
- **Plausible, race**: a publication that is in flight while the team's switch turns off or the team goes private can land after the removal. `remove_team_entries` does not take the per-team advisory lock, and `save_publication` does not re-check the switch or visibility. The window is one pod export.

### Fixed after review

- Defense in depth (superseded by the owner decision below): `can_publish_marketplace_agents` was `team_publisher and team_editor` in `schema.fga` (`schema.fga.json` regenerated with the official `fga` 0.8.1 CLI, which first reproduced the previous JSON byte for byte; REBAC.md and the schema test updated).
- `ImportAgentDialog.tsx` notices use a localized `import.notice` string (`{{capability}}: {{message}}` in English, French spacing in French only).
- The Like button keeps a stable `aria-label`; its state is carried by `aria-pressed` alone (the `unlike` strings are removed).
- A stale-version 409 on the platform admin's removal from the marketplace detail now refetches the detail, so a retry carries the current version (test added).
- The publish dialog hides the quota line when `team.marketplace` is missing instead of showing "0 of 0" (test added).
- The `post_agent_publish` docstring lists `marketplace_agent_inactive`. Regenerating the client gave no tracked diff: `openapi.json` is git-ignored and the RTK client carries no route descriptions.
- A graph agent saved with an empty selection (older saves) now publishes and copies its included defaults (tests in `test_agent_marketplace.py` and `test_agent_copy.py`).
- Team deletion keeps each deleted agent's name on its sessions, as a single deletion does (test in `test_session_agent_name.py`).

Checks after these fixes: fred-core `make test` 1260 passed, 1 skipped; control-plane `make code-quality` pass and `tests/test_agent_marketplace.py` 33 passed; frontend `tsc` and `eslint` pass, `vitest` on the marketplace, team agents and agent card areas 181 passed.

### Owner decision after review (2026-10-12)

The `team_publisher` role was dropped after this review: editors publish, editors and the team admin remove (design.md, "Owner decision: editors publish"). The review above covered the publisher variant; evidence for the editor variant follows (tasks 6.2 and 6.3).

| Check | Result |
| --- | --- |
| control-plane offline suite (`-m "not integration" --disable-socket`) | 1837 passed, 9 skipped, 11 deselected |
| control-plane `ruff check`, `ruff format --check` | pass |
| fred-core offline suite | 1262 passed, 1 skipped, 42 deselected |
| `schema.fga.json` | regenerated with `fga` 0.8.1 (the CLI first reproduced the previous JSON byte for byte) |
| `alembic heads` / SQLite `upgrade head`, `check`, `downgrade base` | one head `24c2f88374fe`; pass |
| dev Postgres `downgrade -2`, `upgrade head`, `alembic check` | pass; only the pre-existing `prompt.command` comment drift |
| frontend `npx tsc --noEmit -p .`, `eslint`, `prettier --check` on changed files | pass |
| frontend `npx vitest run` (full) | 338 files passed, 1 skipped; 4051 tests passed, 7 skipped |
| `scripts/migration_guides.py check-pr --base origin/swift --worktree` | valid, 1 declaration |

The setting columns are renamed `agents_publishing_enabled` in revision `24c2f88374fe` itself (never deployed); the dev database was renamed in place. OpenFGA's Read parses every tuple's relation into `RelationType`, so a leftover `team_publisher` tuple would break team reads once the model changes: the dev store's only such tuple was deleted before the model change. No deployment ever received the role.

### Independent review (2026-10-12)

Second independent review, base `74b2d8129`, head `e3f023ea5`. Manual browser check (task 5.1) run by the product owner on 2026-10-12: passed.

| Finding | Disposition |
| --- | --- |
| M1 secret tuning values in the snapshot (detail and import) | fixed `6da2bc747`: `secret` fields (stored or template declaration) dropped at publish |
| M2 first publication racing a deactivation or suspension | fixed `c1d8c5e3f`: `save_publication` share-locks the agent row, agent before entry |
| L1 import skipped the template visibility check | fixed `1b123c5e0`: 409 `marketplace_template_not_public` for non-admins on import and import targets |
| L2 listing validated every snapshot to read `role` | fixed `8ebf66143`: column subset, `role` by SQL JSON path |
| L3 stale runtime contract reference (§8.106) | fixed `400e86993`: §8.112, renumbered §8.113 after the swift merge |
| L4 issue body out of date | update the #3044 body at push time |
| L5 private team kept published entries if the ReBAC revoke failed | fixed `a8b178e48`: entries removed before the revoke |
| L6 tasks and verification | this section; 5.1 done, 5.2 open until the PR |

After the fixes: control-plane offline suite 1842 passed, 9 skipped, 11 deselected; `tests/test_agent_marketplace.py` 42 passed; `ruff check` and `ruff format --check` pass; no OpenAPI change. Postgres-only locking (M2, as the earlier switch-off re-read) verified by design review only; the SQL `role` extraction was also run read-only on the dev Postgres.

### Not proven

- Postgres-only concurrency (advisory lock, `FOR UPDATE`) is covered by design review only; tests run on SQLite.
