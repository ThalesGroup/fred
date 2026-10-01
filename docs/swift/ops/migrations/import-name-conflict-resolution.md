---
schema: 1
title: "Imports ask before replacing a document of the same name"
impact: minor
configuration: none
configuration_reason: "No configuration key, default or secret changes; the behaviour is unconditional."
after: [2849-k3d-moves-to-deployment-factory, runtime-url-and-tabular-query-safety]
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure. The new
code answers correctly with or without this revision's index; without it, the
question it answers costs a scan of the `metadata` table per imported file,
which is what the index removes.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. The knowledge-flow Alembic upgrade adds one index,
`idx_metadata_document_name`, on the document name inside the `metadata` table's
`doc` column. It is built without `CONCURRENTLY`, so that table is held against
writes while it is built — a few seconds on a large corpus, during which
ingestion waits rather than fails. No existing document is read, rewritten or
re-ingested.

Behaviour change for users, requiring no operator action: uploading a file whose
name a destination folder already holds now asks the uploader to replace the
existing document or keep it. Previously the upload silently created a second
document marked as an alternate version, and a third upload of that name failed
outright.

Any non-UI client of `POST /knowledge-flow/v1/upload-documents` or
`/upload-process-documents` is affected: a conflicting file carrying no decision
is now reported on the response stream with status `conflict` and is not
imported, instead of being versioned silently. Such a client sends its answer as
`conflict_decisions` in `metadata_json` — a map of file name to `overwrite` or
`skip` — or asks `POST /knowledge-flow/v1/documents/name-check` first. The
repository's own ingestion load-test script is the only such client and needs no
change beyond pointing each run at a fresh folder.

Two files of one import can no longer land in the same folder under the same
name. The import dialog refuses the selection and names the collision.

## Validation

Upload a file into a team folder that already holds a document of that name: the
upload dialog lists it and offers **Replace** / **Skip** before anything is sent.
Choosing **Replace** leaves one document in the folder, keeping its identifier,
with the new content.

## Rollback

Downgrading this knowledge-flow Alembic revision drops the index without
changing document data. Release rollback does not undo the later document
renames; follow the alternate-version migration rollback guidance.

## Limitations

The alternate-version migration in this release gives hidden alternates
their own names. Concurrent imports or adding an existing document to a folder
can still create duplicate names; the import then asks the user to rename or
delete one.
