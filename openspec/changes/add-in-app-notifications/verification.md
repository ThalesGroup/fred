## Offline evidence (2026-10-22, branch `feat/notifications`)

Proven (counts below predate the refactor):
- Refactor re-verification: pending
- `apps/control-plane-backend`: `make test` 2055 passed, 10 skipped, 13 deselected; `make code-quality` green (ruff, `ruff check --select I`, format, bandit, detect-secrets, basedpyright 0 errors, 0 warnings); `make db-check-heads` (one head) and `make db-check-sqlite` green (task 9.1).
- `apps/frontend`, in the worktree's own `node_modules` with no Vite running: `make code-quality` (tsc, prettier, eslint) green after ordering one SCSS property; `make test` 363 files passed, 1 skipped; 4464 tests passed, 8 skipped.
- `openspec validate add-in-app-notifications --strict` valid.

## Migration round trip (task 1.3)

Run on the pre-squash revisions (2026-10-22, scratch copy `fred_notif` of the local `fred` database, upgrade / downgrade / upgrade, `alembic current` after each). The squashed revision `83b81adf7450` is covered by the refactor re-verification, still pending.

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
