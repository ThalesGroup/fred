## 1. Backend storage (fred-core)

- [x] 1.1 Add `delete_object(key) -> None` to the `ContentStore` protocol in `libs/fred-core/fred_core/store/base_content_store.py`, documented as idempotent (a missing object is a no-op); verify `make code-quality` in `libs/fred-core` passes type-check.
- [x] 1.2 Implement `delete_object` in `minio_content_store.py` (`remove_object`), `gcs_content_store.py` (`blob.delete()`, `NotFound` swallowed) and `local_content_store.py` (`_safe_under_root(key).unlink(missing_ok=True)`, path traversal still rejected); verify new cases in `fred_core/tests/store/test_{minio,gcs,local}_content_store.py` cover delete-existing, delete-missing and traversal rejection (local).
- [x] 1.3 Add nullable `avatar_object_storage_key: Mapped[str | None]` to `UserRow` in `libs/fred-core/fred_core/users/user_models.py`; verify fred-core tests still pass.
- [x] 1.4 Add `swap_avatar_key(user_id, key | None) -> str | None` (upsert, returns previous key) and `get_avatar_keys(user_ids) -> dict[str, str]` (one `IN` query, non-null keys only, non-UUID ids skipped) to `base_user_store.py` and `postgres_user_store.py`; verify with store tests: first swap creates the row, second swap returns the first key, clear returns the last key, batch read returns only users with a key.

## 2. Backend migration (control-plane)

- [x] 2.1 Create an Alembic revision in `apps/control-plane-backend/alembic/versions/` adding nullable `users.avatar_object_storage_key` (String), with `down_revision` = current single head (re-parent if `swift` moved; never `alembic merge`) and a downgrade that drops the column; verify `make db-check-heads` reports one head and `make db-check-sqlite` (upgrade head, check, downgrade base) passes in `apps/control-plane-backend`.

## 3. Backend API (control-plane)

- [x] 3.1 Create `control_plane_backend/common/avatar_image.py` holding the 5 MB limit, allowed MIME set, extension map, magic-byte detection and `AvatarUploadError`, exposing one function that reads an `UploadFile` and returns `(payload, content_type, extension)`; delete those definitions from `teams/service.py` and `teams/schemas.py`, switch `upload_team_avatar` and the `teams/api.py` handler import to it; verify existing team avatar tests pass unchanged and new unit tests cover empty, oversize, wrong declared type, mismatched magic bytes, and missing filename extension.
- [x] 3.2 Add `avatar_image_url: str | None = None` to `UserSummary` (`users/schemas.py`); verify the schema test or OpenAPI diff shows only the additive optional field.
- [x] 3.3 Add `get_content_store` to `UserDependencies` / `UserServiceDependencies` wired from the same container getter the team dependencies use; verify the app starts in tests (`make test`).
- [x] 3.4 Add a helper in `users/service.py` that attaches picture URLs to a set of summaries (one `get_avatar_keys` call, presign 1 h only for users with a key, all presigns in one `asyncio.to_thread` hop, failed presign leaves the field absent and logs the user id only); call it in `get_users_by_ids` after the Keycloak cache step (URLs never cached); verify tests: mixed batch returns URL only for the user with a key, a key change is visible on the next call despite the name cache, a presign exception yields no URL and no request failure.
- [x] 3.5 Use the same helper for the bootstrap `current_user` (`product/service.py`, inside the existing `asyncio.gather`) (`GET /user` is left unchanged: only the terms-of-use guard reads it); verify a bootstrap test returns `avatar_image_url` for a user with a key and none otherwise.
- [x] 3.6 Add `POST /users/me/avatar` (multipart `file`, 204) in `users/api.py` + service function: validate via 3.1, `put_object` at `users/{uid}/avatar-{uuid}{ext}`, `swap_avatar_key`, then best-effort `delete_object(previous)` (warning without URL/image on failure); verify tests: success sets the key, replace deletes the previous object, invalid upload changes nothing, delete failure of the old object still returns 204.
- [x] 3.7 Add `DELETE /users/me/avatar` (204, idempotent): `swap_avatar_key(None)` then best-effort `delete_object(previous)`; verify tests: delete clears key and object, second delete returns 204 with no store call.
- [x] 3.8 In `delete_user` (`users/api.py`), next to `delete_favorites_for_user` and before the identity-provider deletion, clear the key and delete the object (best effort, warning on failure); verify a test asserts the object delete and key clear for a user with a picture and no store call for one without.
- [x] 3.9 Add both routes to `docs/swift/platform/authz-endpoint-matrix.yaml` as `authenticated_user` (self only, target is always the caller); verify the authz matrix test (part of `make test`) passes.
- [x] 3.10 Grep the new code paths to confirm no log, metric label or audit event carries image bytes, presigned URLs or display names (OBSERVABILITY-AND-AUDIT.md); verify by reviewing the diff of `users/` and `common/avatar_image.py`.

## 4. Frontend API client

- [x] 4.1 Regenerate the control-plane client without wiping a running Vite: `cd apps/control-plane-backend && make generate-openapi`, then `cd apps/frontend && npx --no-install @rtk-query/codegen-openapi src/slices/controlPlane/controlPlaneOpenApiConfig.json` (Node from fnm; the underlying steps of `make update-control-plane-api`, avoiding its `node_modules` prerequisite); verify `controlPlaneOpenApi.ts` gains the two endpoints and `UserSummary.avatar_image_url` and nothing was hand-edited.
- [x] 4.2 In `controlPlaneApiEnhancements.ts`: multipart `query` override for the user avatar upload (copy of the team avatar pattern), `providesTags` `{ControlPlaneUser, "ME"}` on bootstrap and `{ControlPlaneUser, id}` per result on users-by-ids, upload + delete invalidating `ME`, the caller id and `ControlPlaneTeam LIST`; export friendly aliases (`useUploadUserAvatarMutation`, `useDeleteUserAvatarMutation`); verify `npx tsc --noEmit` passes.

## 5. Frontend shared avatar card

- [x] 5.1 Create `shared/molecules/AvatarUploadCard/` (tsx + module.scss) by moving the team avatar card markup, hidden file input, `MAX_AVATAR_SIZE`/`ALLOWED_TYPES` checks, crop state and `AvatarCropEditor` mount out of `TeamSettingsParameters.tsx`; props per design §8 (Delete button only when `onDelete` and `imageUrl`); styles keep `outline-*` borders and full `surface-` token names; verify a vitest covers file-type/size rejection, crop save calling `onUpload`, and Delete visibility.
- [x] 5.2 Switch `TeamSettingsParameters.tsx` to `AvatarUploadCard` without `onDelete`, deleting the inline block, constants, handlers and now-unused SCSS; verify existing team settings tests pass and the rendered card is unchanged.
- [x] 5.3 Use `AvatarUploadCard` on `pages/UserSettingsPage/UserSettingsPage.tsx` with upload + delete, Delete opening the existing `ConfirmationDialog` (fluid content width; any IconButton defaults to `size="medium"` `color="on-surface-retreat"`); verify `UserSettingsPage.test.tsx` covers upload, confirm-delete and cancel-delete.

## 6. Frontend display

- [x] 6.1 Add optional `imageUrl` to `atoms/UserAvatar/UserAvatar.tsx`: `<img>` with intrinsic size and `decoding="async"`, error state falling back to initials, reset when the URL changes; verify a vitest covers image shown, initials without URL, initials after `onError`.
- [x] 6.2 Pass the current user's `avatar_image_url` (bootstrap) to `UserAvatar` in `molecules/UserProfile/UserProfile.tsx`, `UserSettingsPage.tsx`, `layouts/Sidebar/TeamContentNavbar/TeamContentNavbar.tsx` and `molecules/TeamSelectionListItem` (as used by `HomeNavPanel.tsx`); verify existing tests of these components pass and one asserts the image renders when the URL is set.
- [x] 6.3 Pass each admin's `avatar_image_url` in `molecules/AvatarGroup/AvatarGroup.tsx` (consumed by `TeamCard` and `AdminTeamsPage`); verify `TeamCard.test.tsx` covers one admin with a picture and one without.
- [x] 6.4 Add fr + en i18n keys for the user picture card (title, hint, import, empty, delete, confirmation title/body); verify `npx tsc --noEmit` and no missing-key warnings in the touched tests.

## 7. Docs, Help Center and migration note

- [x] 7.1 Add fr + en Help Center content explaining how to set and remove a profile picture (a section in the existing `getting-started/first-steps.md`, next to the profile menu → Settings paragraph, in fr and en); verify `helpCenter/content.test.ts` passes.
- [x] 7.2 Add a dated numbered entry to `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md` (two routes, `UserSummary.avatar_image_url`, self-only rule, object deletion on replace/delete/account deletion, not exported); verify it follows the latest section's format.
- [x] 7.3 Write `docs/swift/ops/migrations/user-profile-picture.md` from `MIGRATION-NOTE-TEMPLATE.md`, impact `minor`: Alembic migration on `users`, content-bucket delete permission (`s3:DeleteObject` / `storage.objects.delete`) recommended, rollback leaves orphan objects, user pictures not exported; verify `make migration-check` passes from the repo root.
- [x] 7.4 Update `docs/swift/ux/COMPONENT-UX.md` for the new `AvatarUploadCard` molecule and the `UserAvatar` image mode; verify the entry names both components.

## 8. Verification

- [x] 8.1 fred-core: `cd libs/fred-core && make test && make code-quality` both green.
- [x] 8.2 control-plane: `cd apps/control-plane-backend && make test && make code-quality && make db-check-heads && make db-check-sqlite` all green.
- [x] 8.3 Alembic against a real Postgres: `make db-upgrade`, `make db-downgrade`, `make db-upgrade` in `apps/control-plane-backend` succeed and `uv run alembic heads` shows exactly one head.
- [x] 8.4 Frontend without wiping a running Vite (warn the developer first; never run through a symlinked worktree `node_modules`): `cd apps/frontend && npx tsc --noEmit && npx prettier --check src && npx eslint src && npx vitest run src/rework/components/shared src/rework/components/pages/UserSettingsPage src/rework/features/helpCenter` all green.
- [x] 8.5 Manual check on a local stack: upload, replace and delete a picture; confirm it appears in the nav rail, settings page, personal-space header, home team list and team-card admins; confirm the old object is gone from MinIO after replace and delete.
- [x] 8.6 Record the exact command outputs in the change (verification evidence) before archiving.
