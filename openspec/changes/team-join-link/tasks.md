## 1. Backend

- [x] 1.1 Add `kind` and `paused` to `PlatformAccessLinkRow` in one linear Alembic revision on the swift head; verify one head and the SQLite upgrade/check/downgrade round-trip.
- [x] 1.2 `PlatformAccessStore.link()`: team links valid only when not paused, Free links only while Free; Free-link administration filtered to `kind = free`.
- [x] 1.3 Single-link service (read, enable/pause, regenerate) and the three `/teams/{team_id}/join-link` routes gated on `can_administer_members` and an own human credential; audit events without the token.
- [x] 1.4 Admission check before any effect on the join endpoints for team links; no joiner rows for team links.
- [x] 1.5 Tests: same URL across toggles, regenerate invalidates the old URL, paused link refused as invalid, non-admitted refusal (service and route, no team name in the body), authorized/Free team never admits, member-only single join, filtering off, kind isolation, personal team, route permissions and audit.

- [x] 1.6 Free admission only from Free-link joiners (request admission, activation preview, whitelist sources); joiner recorded on every Free enrollment; tests for the owner's scenario, Free joiner, leaving, Free removed, authorized team, hand-added member, preview and sources.

## 2. Frontend

- [x] 2.1 Regenerate the control-plane client; replace the team-link hooks in `controlPlaneApiEnhancements.ts`.
- [x] 2.2 `TeamInviteLinkDialog` (switch, URL, Copy with selection fallback, Generate a new link, disabled while paused); restore `PlatformAccessLinkManager` to its original code.
- [x] 2.3 Members tab button for team admins when `platform_access_enabled`; `FreeEnrollmentPage` redirect on `team_link_requires_platform_access`; fr+en strings.
- [x] 2.4 Tests for the dialog, the Members tab button and the join-page redirect.
- [x] 2.6 Copy: `freeHint` and the cleanup confirmation state who Free admits and what cleanup withdraws (fr+en).
- [x] 2.5 Enroll answer carries `team_id` (team and Free links) when the caller is admitted; the join page opens the team's page, `/` without it; backend and frontend tests.

## 3. Docs and close-out

- [x] 3.1 Contract dated entry, endpoint matrix, `COMPONENT-UX.md`, Help Center fr+en, migration note.
- [x] 3.2 Checks and verification evidence below; `openspec validate team-join-link --strict`.

## Verification evidence (2026-10-15, single-link rework)

Branch `feat/team-invite-link` on `origin/swift` at `5cb30c4e5`.

- Control plane: `make db-check-heads` (one head, `c3a7e5d9f1b2` on `24c2f88374fe`), `make db-check-sqlite` passed; `make code-quality` passed (basedpyright 0 errors); `ruff check --select I` clean; `make test`: 1939 passed, 10 skipped (includes `tests/test_team_join_links.py`, 8 tests, and the endpoint matrix).
- fred-core: `fred_core/tests/security/test_platform_access.py` 76 passed; `make code-quality` passed.
- Frontend (worktree's own `node_modules`): `make update-control-plane-api`; `tsc --noEmit`, eslint and prettier clean; vitest on touched areas (team settings, join page, platform-access admin, Help Center): 227 passed. The full suite was not rerun during the owner's test session; the previous full run had only 6 failures, pre-existing on swift (`AgentFormModal*`).
- Root: `make migration-check` valid.
- Not covered: PostgreSQL-only tests (skipped locally); browser check is the owner's.
