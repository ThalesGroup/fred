---
schema: 1
title: "Preserve existing Weaver data when upgrading document-tree views"
impact: minor
configuration: none
configuration_reason: "The existing schema initialization hook and database credentials are reused."
---
## Applicability

Weaver installations with the original matching 0001/schema and 0002/cp read
SQLx history. Historical draft/public schemas and rewritten checksums are not
supported by this upgrade.

## Prerequisites

Back up the Weaver database and verify recovery before deployment. Keep the
original 0001/0002 files unchanged; do not rewrite SQLx history.

## Configuration

No new setting. The k3d pre-upgrade schema hook remains enabled.

## Upgrade

Deploy the updated Control Plane image with the accompanying frontend and consumers.
The existing hook applies 0003/cp read document tree in a SQLx transaction. It appends
display columns to three cp_read views, preserving data and reader grants. A five-second
lock timeout fails safely under contention; retry after the blocker ends.

## Validation

Verify successful migrations 1, 2 and 3 with unchanged fingerprints for 1 and 2,
healthy application pods, retained documents and grants, and the document-tree columns.
Disposable PostgreSQL regressions cover upgrade/replay and incompatible-history
rejection. No S3 or OpenSearch mutation is part of this migration.

## Rollback

Older binaries require an exact migration history and may refuse to restart after
0003. Prefer a forward fix. Recovery from the backup requires a coordinated application
and database rollback, with an explicit plan for writes since the backup; never delete
history rows or rewrite checksums to force an old binary to start.

## Limitations

This adds no general conversion for draft schemas. The API remains read-only with
respect to schema initialization; only the explicit command/hook applies migrations.
