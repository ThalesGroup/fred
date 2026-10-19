---
schema: 1
title: "Store and retrieve immutable originals through Rust manager"
impact: major
configuration: production
configuration_reason: "Optional storage.content configures S3 credentials, limits and an API-only bounded temporary volume; the generated chart schema includes this contract."
---

## Applicability

The Rust manager reconstruction on `chore/rust-rebac`. Resources creates originals
in manager folders and downloads them without ingestion. This does not migrate
Swift/Knowledge Flow documents, tags, tasks or identifiers.

## Prerequisites

Migration 0008 requires an empty manager document registry. It deliberately refuses
metadata-only rows before changing schema and never deletes them automatically.
If such rows exist, retain coordinated backups and resolve them through an explicitly
approved PoC reset or migration before upgrading. Existing organizations, roles and
folders can remain when the document registry is empty.

## Configuration

Content storage is optional and disabled by omission. To activate it, provision a
private bucket with versioning never enabled, Object Lock disabled and no enabled
lifecycle policy. Grant Put/Get/Delete/List and bucket configuration inspection to
manager. Keep these policies unchanged during operation.

Use `deploy/charts/fred/examples/document-storage.yaml` as an instance overlay,
replacing endpoint/bucket and existing Secret references. HTTPS is required except
for explicitly configured local HTTP. Set API ephemeral resources for the bounded
spool plus runtime/log overhead. Preserve the existing control-plane image, service,
configuration and worker contract. No Temporal/ingestion configuration is required
for this journey.

## Upgrade

Back up SQL/OpenFGA and any existing object namespace. Stop old manager writers,
apply the normal migration hook and deploy API/frontend together. The API verifies
the bucket and creates a database-bound namespace before serving. A bucket or
namespace mismatch refuses startup rather than adopting unknown objects.

## Validation

An editor uploads to an existing Resources folder, reloads and downloads identical
bytes. A same-name import conflicts without replacement. A reader downloads but
cannot upload; an admin alone cannot read. Storage succeeds with processing services
unavailable. Check receipt recovery and cleanup backlog through manager.

## Rollback

Migration 0008 changes the document storage contract. Do not run the previous writer
against newly stored originals. Restore a coordinated SQL/OpenFGA/object backup and
matching binaries when rollback is necessary. Disable uploads and cleanup while
restoring the SQL/object pair; re-enable only after consistency validation.

## Limitations

Individual files and browser downloads are capped at 100 MiB. Stored means retained,
not indexed. Replacement, document deletion, processing, preview and bulk ZIP are
outside this storage contract. The complete Swift-to-PoC migration is a separate job.
