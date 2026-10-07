## Why

A person is shown everywhere in Fred as initials only. Teams can already carry an uploaded avatar, but people cannot, so the navigation rail, the personal space and the team administrator lists all look the same for everyone. The team avatar flow (upload, square crop, preview) already exists and can serve people without new UI concepts.

Tracking: GitHub issue #2977.

## What Changes

- **Upload and delete a profile picture.** On the user settings page, a person uploads a picture with the same card, upload button, preview and crop dialog as the team avatar. A Delete button, behind a confirmation, removes it. Without a picture the initials are shown, as today.
- **Shared avatar upload card.** The team avatar card, upload button and preview move out of the team settings parameters into one shared component. Team settings use it with unchanged behaviour (no delete for team avatars). The crop dialog is reused unchanged.
- **The picture is shown wherever a person's initials are shown today:** the navigation-rail profile, the user settings page, the personal-space header, the personal entry of the home team list, and team administrator avatars on team cards and the admin teams page. Places that show a name as text only are unchanged. A picture that fails to load falls back to the initials.
- **Old pictures are really deleted** from object storage when a picture is replaced, deleted, or when the account is deleted. The object store contract gains a delete operation, implemented for every storage backend.
- **API.**
  - New `POST /users/me/avatar` (multipart) and `DELETE /users/me/avatar` (idempotent). Only the person themselves can set or delete their picture.
  - Upload validation is the same as for team avatars, shared rather than copied: 5 MB maximum, JPEG/PNG/WebP, declared type must match the file's actual content.
  - The user summary returned by Control Plane APIs gains an optional `avatar_image_url`: present for the bootstrap's current user, `GET /users/by-ids` and team administrator summaries.
- **Storage.** The `users` table gains a nullable column holding the picture's object key (Alembic migration, single head).
- **Not exported.** Platform export/import does not carry user pictures: it does not export people at all today.
- **Help Center.** fr and en pages explain how to set and remove a profile picture.

## Capabilities

### New Capabilities

- `user-profile-picture`: a person's own profile picture — who may set or delete it, upload validation, where it is returned and displayed, the initials fallback, and its removal from storage on replace, delete and account deletion.

### Modified Capabilities

None. Team avatar behaviour does not change; only its UI component is shared.

## Impact

- **fred-core:** object store contract gains a delete operation (MinIO/S3, GCS, local disk); `users` row model gains the picture key column; user store gains read/write of that key, including a batched read for many ids.
- **Control plane:**
  - two new routes under `/users/me/avatar`;
  - upload validation helper shared between team and user avatars;
  - `UserSummary` gains `avatar_image_url` (additive, optional);
  - account deletion removes the picture object;
  - Alembic migration on `users`;
  - `authz-endpoint-matrix.yaml` entries; dated contract entry in `CONTROL-PLANE-PRODUCT-CONTRACT.md`.
- **Frontend:**
  - regenerated control-plane client; multipart upload override and delete mutation;
  - shared avatar upload card used by team settings and user settings;
  - `UserAvatar` accepts an optional image URL;
  - fr/en i18n strings and Help Center pages.
- **Operations:** minor migration note — new database migration, and the control plane now deletes objects in the content bucket, so its storage credentials need delete permission there.
- **Privacy/observability:** picture bytes, presigned URLs and display names are never written to logs, metrics or audit events.
