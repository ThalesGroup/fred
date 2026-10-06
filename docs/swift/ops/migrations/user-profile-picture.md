---
schema: 1
title: "People can set their own profile picture"
impact: minor
configuration: none
configuration_reason: "No configuration key, default or chart value changes; pictures use the existing control-plane content bucket and its credentials."
---
## Applicability

All Fred deployments upgrading the control-plane backend and frontend.

## Prerequisites

Grant the control plane's content-bucket credentials permission to delete
objects, in addition to the read and write they already need:

- MinIO / SeaweedFS / S3: `s3:DeleteObject` on the content bucket.
- GCS: `storage.objects.delete` on the content bucket.

Without it, uploads and deletions still succeed, but each replaced or removed
picture stays in the bucket and the control plane logs a warning naming the
user id.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. The control-plane Alembic migration `aac66348e27b` adds
the nullable column `users.avatar_object_storage_key`; it runs with the usual
migration step and needs no backfill, since everyone starts without a picture.

## Validation

Open **Profile → Settings**, import a picture and save the crop: it appears in
the navigation panel. Replace it, then delete it, and check in the content
bucket that no object remains under `users/<your user id>/`.

## Rollback

Downgrade the control-plane migration to `b4e8d2a9c613` (drops the column),
then roll back the images. Pictures already uploaded stay in the content bucket
under `users/`, unreferenced; delete that prefix by hand if needed.

## Limitations

- Profile pictures are not part of the platform export/import: people are not
  exported, so after an import into a new platform everyone starts without a
  picture.
- The local filesystem content store serves no URLs, so pictures are stored but
  initials stay displayed, as for team avatars.
- When the Keycloak admin client is not configured, team administrator
  summaries carry no names and no pictures.
