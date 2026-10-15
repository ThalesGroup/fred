## 1. Backend model and migration

- [x] 1.1 Add `kind` (`free` | `team`, server default `free`) to `PlatformAccessLinkRow` and one linear Alembic revision on the current swift head; verify `alembic heads` shows one head and a real `alembic upgrade head` / `downgrade -1` round-trip.
- [x] 1.2 Make `PlatformAccessStore.link()` kind-aware (`free` requires the Free flag, `team` does not); verify with store tests for both kinds, revoked, expired, personal team.

## 2. Backend service and routes

- [x] 2.1 Thread `kind` through create/list/joiners/reveal/revoke/cleanup so each family only sees its own kind; verify a link id of the other kind answers 404 and cleanup leaves the other kind untouched.
- [x] 2.2 Add the six `/teams/{team_id}/join-links` routes gated on `can_administer_members`; verify team admin allowed, member/non-member/platform-admin-only refused, personal team refused, reveal requires an own human credential.
- [x] 2.3 Enrollment, preview and opening on a `team` link require `PlatformAccess.admitted` before any write; verify: admitted caller joins as `team_member` only; non-admitted caller gets `403 team_link_requires_platform_access` with no team name, no membership, no admission, no counter change; joining an authorized or Free team through a `team` link never admits; already-member is a no-op without event; filtering off admits every authenticated caller.
- [x] 2.4 Audit: `kind` on existing link events, `team.join_link.joined` on a new join; verify events in tests and that no token is logged.

## 3. Frontend

- [x] 3.1 Regenerate the control-plane client (`make update-control-plane-api`).
- [x] 3.2 Extract the shared link manager from `PlatformAccessLinkManager`; verify the existing admin tests pass unchanged.
- [x] 3.3 Add the "Invite link" action next to "Add members" in `TeamSettingsMembers`, team admins only; tests for visibility and opening the manager.
- [x] 3.4 `FreeEnrollmentPage`: on `403 team_link_requires_platform_access`, replace the location with the existing refusal screen; test.
- [x] 3.5 Update the stale comment in `TeamSettingsParameters`; fr+en strings.

## 4. Docs and close-out

- [x] 4.1 `CONTROL-PLANE-PRODUCT-CONTRACT.md` dated entry; `COMPONENT-UX.md`; Help Center `features/teams-and-permissions.md` fr+en.
- [x] 4.2 Migration note (operations: schema migration) per `MIGRATION-GUIDES.md`.
- [x] 4.3 `make code-quality`, `make test`, ruff import order, basedpyright; record evidence; `openspec validate team-join-link --strict`.

## Verification evidence (2026-10-15)

Branch `feat/team-invite-link`, on `origin/swift` at `5cb30c4e5`.

- Control plane (`apps/control-plane-backend`): `make db-check-heads` (single head `c3a7e5d9f1b2`, parent `24c2f88374fe`); `make db-check-sqlite` (upgrade head, `alembic check`, downgrade base) passed; `make code-quality` passed (ruff, format, bandit, basedpyright 0 errors); `ruff check --select I` clean; `make test` (offline, final state): 1939 passed, 10 skipped; it includes `tests/test_team_join_links.py` (8 new) and the endpoint matrix, which now lists the six routes in `docs/swift/platform/authz-endpoint-matrix.yaml`.
- fred-core: `fred_core/tests/security/test_platform_access.py` 76 passed; `make code-quality` passed.
- Frontend (worktree's own `node_modules`): `make update-control-plane-api`; `make code-quality` (tsc, prettier, eslint) passed; full `vitest run`: 4327 passed, 6 failed in `AgentFormModal.names.test.tsx` and `AgentFormModalAssistant.test.tsx`, which fail identically on unmodified `origin/swift` (missing redux Provider), unrelated to this change. New tests: join page refusal redirect (preview and enroll), team-scope link manager, Members tab action visibility.
- Root: `make migration-check`: 1 new declaration valid.
- Not covered: PostgreSQL-only concurrency tests (skipped locally, no PostgreSQL started); no manual browser test.
