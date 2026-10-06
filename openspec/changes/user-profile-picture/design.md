## Context

See proposal.md for motivation and specs/user-profile-picture/spec.md for the behaviour contract. Current state that shapes the approach:

- **Team avatars** are uploaded through `upload_team_avatar` in `control_plane_backend/teams/service.py`. Validation lives there: `_MAX_AVATAR_FILE_SIZE_BYTES`, `_ALLOWED_AVATAR_MIME_TYPES`, `_AVATAR_EXTENSION_BY_MIME`, `_detect_image_content_type`, and `AvatarUploadError` in `teams/schemas.py`. The 400 handler is registered app-wide in `teams/api.py`. Keys are `teams/{id}/avatar-{uuid}{ext}`. Replacing an avatar leaves the old object in the bucket.
- **Presigning:** `_build_team_dto` presigns with a 1 h TTL. `MinioContentStore.get_presigned_url` signs locally on a stable time grid, so the URL is cacheable (see `docs/swift/ops/migrations/team-avatar-loading.md`). `GcsContentStore.get_presigned_url` makes two network calls per object (`blob.exists` and IAM `signBlob`) and is never cacheable. `LocalContentStore` raises `NotImplementedError`. All three are synchronous.
- **ContentStore** (`libs/fred-core/fred_core/store/base_content_store.py`) has only `put_object` and `get_presigned_url`.
- **`users` table** (`UserRow` in `libs/fred-core/fred_core/users/user_models.py`) has one row per person, but only once that person has accepted the terms of use or used personal storage. Rows are created lazily: see `update_gcu_version` and `increment_current_storage_size` in `postgres_user_store.py`.
- **User summaries:**
  - `users/service.py::get_users_by_ids` resolves names from Keycloak, with a 5-minute in-process cache per id. It backs `GET /users/by-ids` and, through `TeamServiceDependencies.get_users_by_ids`, the team admin summaries (team list and single team), member lists and platform-role holders.
  - The bootstrap's `current_user` is built from the token by `UserSummary.from_keycloak_user` in `product/service.py`.
  - `GET /user` builds `currentUser` inline. Only the terms-of-use guard reads it, so it does not carry the picture.
- **Frontend:**
  - The team avatar card, upload button and preview are inline in `TeamSettingsParameters.tsx`, which also holds the client-side checks (`MAX_AVATAR_SIZE`, `ALLOWED_TYPES`), `handleFileSelect` and `handleCropSave`.
  - `AvatarCropEditor` is generic.
  - `UserAvatar` renders initials only.
  - `GET /users/by-ids` has no cache tags. Bootstrap provides only `ControlPlaneTeam` tags.
- Platform export never writes people (`import_export/exporter.py`: "This export never writes users.json").

## Goals / Non-Goals

**Goals:**
- One validation path for team and user avatars. Moving the constants out of `teams/service.py` deletes the team-only copy and adds no second one.
- No orphan user-picture objects in normal operation.
- Picture URLs added to summaries cost at most one database query per batch, plus one presign per person who actually has a picture.

**Non-Goals:**
- Deleting team avatars, or cleaning up the orphaned team avatar objects left by past replacements.
- Making GCS presigned URLs cacheable, or changing the presigning strategy (tracked separately in #2394).
- Pictures for service accounts or for ids that are not UUIDs.
- Serving pictures through the local filesystem store. Like team avatars, a picture there gets no URL and the initials stay.
- Showing pictures in member lists, platform-role tables or any text-only place. Those summaries may carry the URL, but no UI change is made there.

## Decisions

### 1. `delete_object` on the ContentStore contract, idempotent

Add `delete_object(key) -> None` to the protocol and to all three stores. Deleting a missing object is a no-op:
- MinIO: S3 `remove_object` already behaves this way.
- GCS: `blob.delete()` with `NotFound` swallowed.
- Local: `_safe_under_root(key).unlink(missing_ok=True)`.

Idempotence lets replace, delete and account deletion call it without first checking that the object exists.

Alternative considered: a lifecycle or sweeper job that removes unreferenced objects. Rejected: it adds a moving part, and the developer asked for real deletion.

### 2. Shared avatar validation in `control_plane_backend/common/avatar_image.py`

Move the size limit, the allowed MIME set, the extension map, `_detect_image_content_type` and `AvatarUploadError` into one module. It exposes one function: read an `UploadFile` and return the validated `(payload, content_type, extension)` or raise `AvatarUploadError`. Both `upload_team_avatar` and the new user upload call it.

The existing app-wide exception handler keeps mapping the error to 400. Only its import moves. The team flow's behaviour and error messages do not change.

Alternative considered: importing the private helpers from `teams/service.py` into `users/`. Rejected: it would make `users` depend on team internals.

### 3. Store write order: new object, then key, then old object

- **Upload:**
  1. `put_object` the new key `users/{uid}/avatar-{uuid}{ext}`.
  2. Atomically swap the key in `users` and get the previous key back. The swap is an upsert, because the row may not exist yet.
  3. `delete_object(previous)`, best effort.
- **Delete:**
  1. Atomically clear the key and get the previous one back.
  2. `delete_object(previous)`, best effort.
- **Account deletion** (`users/api.py::delete_user`): placed next to `delete_favorites_for_user`, before the identity-provider account is deleted, so a failure there is retried rather than orphaned. It clears the key and deletes the object.

A failed old-object delete only logs a warning with the user id and the storage error. It never logs the URL or the image.

The UUID in the key gives each picture a new URL, which is how browsers drop the cached copy.

Alternative considered: a fixed key per user, overwritten on each upload. Rejected: the stable presign grid would keep serving the cached old image for up to a quarter of the TTL.

### 4. User store API

`BaseUserStore` / `PostgresUserStore` gain:
- `swap_avatar_key(user_id, key | None) -> str | None`: upsert, returns the previous key.
- `get_avatar_keys(user_ids) -> dict[str, str]`: one `SELECT id, avatar_object_storage_key ... WHERE id IN (...) AND avatar_object_storage_key IS NOT NULL`.

Ids that are not UUIDs are skipped before the query.

### 5. Picture URLs are attached outside the display-name cache

`get_users_by_ids` keeps caching Keycloak names. After the cache and Keycloak step, a single helper attaches `avatar_image_url`:
1. one `get_avatar_keys` call for the returned ids;
2. one presign per key, 1 h TTL like team avatars;
3. a failed presign leaves the field absent.

Because the URL is never cached with the name, an upload or delete shows up on the very next summary.

Attaching the URL inside `get_users_by_ids` covers `/users/by-ids` and the team admin summaries from one place, rather than repeating it at each call site. Member lists and platform roles also receive the field, which is harmless and additive.

The bootstrap's `current_user` uses the same helper for a single id. In bootstrap, that read joins the existing `asyncio.gather`.

The presigns for one batch run in a single `asyncio.to_thread` hop, so GCS network calls never block the event loop. MinIO signs locally, and a thread hop per batch rather than per user keeps its overhead negligible.

Alternative considered: storing the URL in the 5-minute cache. Rejected: it would serve a deleted object's URL for up to 5 minutes.

### 6. Routes and authorization

- `POST /users/me/avatar` (multipart, field `file`, returns 204).
- `DELETE /users/me/avatar` (returns 204, idempotent).

Both use `get_current_user`, and the target is always `user.uid`, so there is no path parameter that could name someone else. No ReBAC check is needed beyond authentication. Both are recorded in `authz-endpoint-matrix.yaml` as `authenticated_user`, self only.

Neither path collides with the `/users/{user_id}` routes: the extra segment never matches `DELETE /users/{user_id}`. `UserDependencies` gains `get_content_store`, wired from the same container getter the team dependencies use.

### 7. `UserSummary.avatar_image_url: str | None = None`

The field is additive and optional. Routes that use `response_model_exclude_none` (such as `/users/by-ids`) omit it when a person has no picture; the others return `null`. The name matches the team field. A dated entry in `CONTROL-PLANE-PRODUCT-CONTRACT.md` records it.

### 8. Frontend: one `AvatarUploadCard` molecule, `UserAvatar` gains `imageUrl`

- **`shared/molecules/AvatarUploadCard`** takes over from `TeamSettingsParameters.tsx`: the markup, the hidden file input, the client checks, the crop dialog state and the `AvatarCropEditor` mount.
  - Props: `title`, `hint`, `importLabel`, `emptyLabel`, `imageUrl`, `onUpload(blob)` (a promise), `uploading`, optional `onDelete` and `deleting`. The Delete button renders only when `onDelete` is given and `imageUrl` is set.
  - Team settings pass no `onDelete`, so their behaviour is unchanged.
  - The user settings page passes `onDelete`, which opens the existing `ConfirmationDialog`.
  - The team-specific SCSS for this block moves with the component, using `outline-*` borders and full `surface-` token names.
- **`UserAvatar`** gets an optional `imageUrl`. It renders an `<img>` with intrinsic size and `decoding="async"`, as the team avatar does, and holds an error state that falls back to initials. The error state resets when the URL changes.
  - Call sites pass the URL from `current_user` (bootstrap) or from each `UserSummary` (`AvatarGroup` admins).
- **RTK Query:**
  - Bootstrap also provides `{ControlPlaneUser, "ME"}`.
  - `useUsersByIdsQuery` provides `{ControlPlaneUser, id}` per returned user.
  - Upload and delete invalidate `ME`, the caller's id, and `ControlPlaneTeam LIST`, because team cards carry admin pictures.
  - The upload override copies the team multipart pattern in `controlPlaneApiEnhancements.ts`.

Alternative considered: a second, user-only card. Rejected: it duplicates the team markup, which goes against the consolidation phase.

### 9. Import/export: out of scope

Export does not carry people, so it has nothing to attach pictures to. Pictures are personal data, owned by the person rather than the platform. After an import into a fresh platform, people start without pictures.

## Risks / Trade-offs

- [GCS presign costs two network calls per person with a picture: up to 100 in `/users/by-ids`, and every admin with a picture on each team-list load] → presign only people who have a key, with one thread hop per batch. The cost is the same per object as team avatars today. A cacheable or cheaper GCS strategy belongs to #2394.
- [The storage credentials of existing deployments may lack delete permission] → the old-object delete is best effort and logs a warning, so uploads keep working. The migration note asks operators to grant `s3:DeleteObject` / `storage.objects.delete` on the content bucket.
- [The object delete fails during account deletion, leaving an orphan with no key] → a warning is logged with the user id. Accepted: it is rare, and it is never visible to anyone.
- [When Keycloak M2M is disabled, `get_users_by_ids` returns nothing, so admin summaries carry no picture] → accepted. It matches the existing fallback, under which names are missing too.
- [A browser keeps a cached image after a replace] → each picture gets a new UUID key, hence a new URL.

## Migration Plan

1. Alembic revision adding a nullable `users.avatar_object_storage_key` (String). Its `down_revision` is the current control-plane head at implementation time; re-parent it if `swift` moves. Downgrade drops the column.
2. Deploy normally. No backfill: everyone starts without a picture.
3. Rollback: downgrade the migration. Uploaded picture objects stay in the bucket, unreferenced. The migration note says so.
4. Migration note `docs/swift/ops/migrations/user-profile-picture.md`, impact `minor`: there is a database migration, and delete permission on the content bucket is recommended.

## Implementation notes (2026-10-06)

Divergences found while implementing, all small:

- **Base moved.** `swift` gained the local user directory (#2862) on the same
  user files while this change was planned; the unpublished branch was rebased
  before coding. The migration's parent is therefore `a7e9c2d41063` (configurable GCU versions, #2974).
- **Local user directory.** There, `delete_user` only suspends the account and
  returns before `delete_favorites_for_user`, so the picture is kept like the
  favorites; the identity-provider path deletes it as designed. Local-directory
  summaries from `get_users_by_ids` get pictures through the same helper.
- **Ids that are not UUIDs.** Upload answers 400 (`AvatarUploadError`), delete
  and account deletion are no-ops.
- **Storage calls off the event loop.** `put_object` and `delete_object` run in
  `asyncio.to_thread` in the user flow (the team flow is unchanged).
- **Cache tags.** The upload/delete mutation args do not carry the caller's id,
  so both invalidate the whole `ControlPlaneUser` tag type (covers `ME` and the
  caller's id) plus `ControlPlaneTeam LIST`.
- **`AvatarUploadCard`** takes a `deleteLabel` prop next to `onDelete`.
- **Spec wording.** The summary requirement no longer lists the current-user
  details endpoint, matching the decision that `GET /user` stays without the
  picture.

## Open Questions

None — `GET /user` stays without the picture and the Help Center section goes in `getting-started/first-steps.md` (developer decisions).
