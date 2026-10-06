## Verification evidence (2026-10-06)

Branch `feat/user-profile-picture`, rebased on `origin/swift` at `ee1c521ee`
(adds `ba2c3c7fd0c1`, retire legacy MCP document search); the picture migration
`aac66348e27b` now revises it. Re-run after the review fixes (smaller crop,
presign scope, Safari type, error toasts, MIME extension) and the last rebase.

| Area | Command | Result |
| --- | --- | --- |
| fred-core | `cd libs/fred-core && make test` | 1105 passed, 42 deselected |
| fred-core | `make code-quality` | ruff, format, bandit, basedpyright: 0 errors |
| control-plane | `cd apps/control-plane-backend && make test` | 1559 passed, 11 deselected |
| control-plane | `make code-quality` | 0 errors |
| Alembic | `make db-check-heads` | single head `aac66348e27b` |
| Alembic | `make db-check-sqlite` | upgrade head (`ba2c3c7fd0c1 -> aac66348e27b`), check, downgrade base passed |
| Alembic | `make db-check-postgres-full` (throwaway Postgres on 5433) | upgrade head, check, downgrade base passed (before the last rebase; SQLite re-run after it) |
| API client | `cd apps/frontend && make update-control-plane-api` (services stopped) | no diff against the rebased `controlPlaneOpenApi.ts` |
| frontend | `npx tsc --noEmit`, `npx prettier --check src`, `npx eslint src` | clean (tsc re-run after the last rebase) |
| frontend | `npx vitest run src/rework/components/shared src/rework/components/pages/UserSettingsPage src/rework/components/pages/admin/AdminTeamsPage src/rework/features/helpCenter src/locales` | 96 files, 1162 tests passed |
| docs | `make migration-check` | 1 new declaration valid |
| performance | `fred-performance-reviewer` on the presign change | no blocking finding; see below |

Frontend `make` targets were not run (they wipe `node_modules/.vite`); the
commands above are their underlying checks.

Not run against the shared dev database: its control-plane revision belongs to
another branch, so `make db-upgrade` / `db-downgrade` there were replaced by the
throwaway Postgres check above.

### What the tests prove

- Content stores: `delete_object` removes an existing object and ignores a
  missing one on MinIO, GCS and local disk; local rejects path traversal.
- User store (SQLite): first swap creates the row, each swap returns the
  previous key, clearing a missing user creates no row, the batch read returns
  only users with a key and skips non-UUID ids.
- Shared validation: empty, oversize, GIF, mismatched magic bytes, unknown
  bytes rejected; the key extension follows the detected type even when the
  filename says otherwise (PNG sent as `avatar.webp` gets `.png`).
  Existing team avatar tests pass unchanged.
- Summaries: a mixed batch gets one key query and a URL only for the person
  with a key, cached summaries are not mutated, the generic `get_users_by_ids`
  carries no URL and reads no key, a key change shows despite the name cache,
  20 presigns overlap but never exceed the bound of 8, team admin summaries
  from `_enrich_teams_with_membership` carry the URL, a failed presign omits
  the URL and logs the user id without URL. Bootstrap `current_user` carries
  the URL only when a key exists.
- Routes: upload sets the key, replace deletes the old object, invalid upload
  changes nothing, an old-object delete failure still returns 204, a non-UUID
  account gets 400, delete is idempotent; account deletion removes the picture
  before the identity account and makes no store call without one. Both routes
  are in the authz matrix (`test_authz_endpoint_matrix`).
- Frontend: `AvatarUploadCard` file checks with an error toast, crop upload as
  `avatar.webp`/`image/webp` or `avatar.png`/`image/png` when the browser
  falls back to PNG, a failed upload toast with the server's reason, and Delete
  visibility; user settings report a failed delete;
  `UserAvatar` image, initials and error fallback; user settings upload,
  confirmed delete and cancelled delete; navbar personal picture; team-card
  admins with and without a picture.

### Manual check (task 8.5)

Local stack on this branch, SeaweedFS S3 storage, 2026-10-06: the developer
uploaded, replaced and deleted a picture and saw it in every place listed in
the spec. Afterwards the migration chain `c4d7e2a91b30 -> b4e8d2a9c613 ->
aac66348e27b` applied on startup, and `control-plane-content-objects` held
exactly one object under `users/<uid>/`, the one the users row references.

### Performance review (presign change)

- Presigns run in `asyncio.to_thread` under a per-batch semaphore of 8
  (`users/service.py::_presign_avatar_urls`), so GCS network calls never block
  the event loop. Only team admin summaries and the bootstrap user pay for
  them now; member lists, platform roles and `/users/by-ids` pay nothing.
- No new metric, label or log field; no new in-memory state.
- Bootstrap makes up to three key queries (team list admins, the personal team,
  the current user), all inside its existing `asyncio.gather`.
- Pre-existing, not changed here: team avatars are still presigned inline on
  the event loop in `teams/service.py::_build_team_dto` (two blocking network
  calls per team on GCS). `GcsContentStore._mint_access_token` caches
  credentials without a lock, so concurrent presign threads may refresh twice
  (redundant, not incorrect).

### Not proven yet

- GCS presign latency and default thread-pool pressure for many concurrent
  team-list loads whose admins have pictures (each batch holds up to 8 pool
  threads); needs a load test on a GCS deployment.
- The Safari PNG fallback is covered by unit tests only, not checked in a real
  Safari.
