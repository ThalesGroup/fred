## Verification evidence (2026-10-06)

Branch `feat/user-profile-picture`, rebased on `origin/swift` at `287b5207f`.

| Area | Command | Result |
| --- | --- | --- |
| fred-core | `cd libs/fred-core && make test` | 1098 passed, 40 deselected |
| fred-core | `make code-quality` | ruff, format, bandit, basedpyright: 0 errors |
| control-plane | `cd apps/control-plane-backend && make test` | 1544 passed, 8 deselected |
| control-plane | `make code-quality` | 0 errors |
| Alembic | `make db-check-heads` | single head `aac66348e27b` |
| Alembic | `make db-check-sqlite` | upgrade head, check, downgrade base passed |
| Alembic | `make db-check-postgres-full` (throwaway Postgres on 5433) | upgrade head, check, downgrade base passed |
| frontend | `npx tsc --noEmit`, `npx prettier --check src`, `npx eslint src` | clean |
| frontend | `make code-quality` | clean |
| frontend | `npx vitest run src/rework/components/shared src/rework/components/pages/UserSettingsPage src/rework/features/helpCenter` | 94 files, 1142 tests passed |
| docs | `make migration-check` | 1 new declaration valid |

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
  bytes rejected; missing filename extension falls back to the MIME extension.
  Existing team avatar tests pass unchanged.
- Summaries: a mixed batch gets one key query and a URL only for the person
  with a key, cached summaries are not mutated, a key change shows despite the
  name cache, a failed presign omits the URL and logs the user id without URL.
  Bootstrap `current_user` carries the URL only when a key exists.
- Routes: upload sets the key, replace deletes the old object, invalid upload
  changes nothing, an old-object delete failure still returns 204, a non-UUID
  account gets 400, delete is idempotent; account deletion removes the picture
  before the identity account and makes no store call without one. Both routes
  are in the authz matrix (`test_authz_endpoint_matrix`).
- Frontend: `AvatarUploadCard` file checks, crop upload and Delete visibility;
  `UserAvatar` image, initials and error fallback; user settings upload,
  confirmed delete and cancelled delete; navbar personal picture; team-card
  admins with and without a picture.

### Manual check (task 8.5)

Local stack on this branch, SeaweedFS S3 storage, 2026-10-06: the developer
uploaded, replaced and deleted a picture and saw it in every place listed in
the spec. Afterwards the migration chain `c4d7e2a91b30 -> b4e8d2a9c613 ->
aac66348e27b` applied on startup, and `control-plane-content-objects` held
exactly one object under `users/<uid>/`, the one the users row references.

### Not proven yet

- GCS presign latency for teams with many admins who have pictures (presigns of
  one batch run sequentially in one thread hop); needs a load test on a GCS
  deployment.
