## Final verification (2026-10-22, branch `feat/notifications`)

Branch rebased on `origin/swift` (merge base `9d85f3ae7`); covers the squashed revision `83b81adf7450` and the quality refactor (section 11).
- `apps/control-plane-backend`: `ruff check`, `ruff check --select I`, `ruff format --check` clean; basedpyright with baseline, 0 errors; `pytest -m "not integration"`: 2096 passed, 10 skipped, 14 deselected; `alembic heads`: single head `83b81adf7450`.
- Postgres (owner-run, throwaway database `fred_migcheck`): `alembic upgrade head` from empty, `alembic check` clean, `alembic downgrade c9acb7dd3ad0`, `alembic upgrade head` again; `tests/test_notification_store_postgres_integration.py -m integration_postgres`: 1 passed.
- `apps/frontend`: `tsc --noEmit` clean; eslint and prettier clean on the changed files; full `vitest run`: 366 files passed (1 skipped), 4547 tests passed, 8 skipped.
- Owner live checks on two users (Vite :5174 + test control plane) through the review rounds.
- `openspec validate add-in-app-notifications --strict` and `openspec validate add-team-join-requests --strict` valid.

## Live check (task 9.4, 2026-10-22, owner-run)

Two users, worktree frontend on Vite :5174, worktree control-plane on :8223 (`fred_notif`, memory scheduler), shared local fred-agents and knowledge-flow. Confirmed:
- B edits an agent A published: A's badge appears; opening the popover resets it.
- Clicking the tile opens the edited agent.
- B republishes: A's tile shows "Handled by B".
- A platform admin removes the entry: A gets the removal tile with the reason.
- Full text shown (no truncation); delete one and clear all work.
- Rail layout: profile on top, bell below, divider.

A second user's CGU 403 during the test came from the split setup (fred-agents reads the `fred` database, the test control-plane wrote to `fred_notif`), not from this change.

## Dismiss on action (task 7.6, 2026-10-22)

`npx vitest run src/rework/features/notifications src/rework/components/shared/molecules/NotificationTile`: 4 files, 44 tests passed; `npx tsc --noEmit` and `npx eslint` on the touched files clean. The close button's visibility without hover is a CSS rule (no hover-only `visibility: hidden` left); happy-dom does not compute it, so the test pins the rendered button only.

## Not proven

- Rows created before a permission is removed by a direct OpenFGA edit (outside the control-plane role and membership routes) stay until they are handled or expire after 30 days.
- Summary polling across several control-plane replicas was not load-tested; the summary is one `count(*)` on the partial unseen index per visible tab every 15 s.
- Per-type counts reach OpenSearch only: `notification_type` is not in `PROMETHEUS_ALLOWED_LABELS` (task 9.3).
