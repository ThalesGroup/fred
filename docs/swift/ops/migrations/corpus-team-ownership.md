---
schema: 1
title: "Convert corpus folders to verified team ownership"
impact: major
configuration: none
configuration_reason: "Ownership conversion uses the deployment's existing SQL and OpenFGA connections."
---

## Applicability

This is the ownership step of the coordinated corpus cutover for #2845.

The tool converts verified user owners into their canonical personal teams.
Existing explicit team owners stay unchanged. Folder IDs, document membership,
files and authorization tuples are not changed by this step.

## Prerequisites

Drain ingestion and stop all corpus writers, workers and ownership/grant writers
for the maintenance window. Back up PostgreSQL and OpenFGA together using the
deployment's normal procedure. Retain the old folder owner tuples until this
step has completed. Never infer owners from document uploaders or visible results.

Use the deployment's knowledge-flow configuration and connections. From the
repository root, inspect the proposed mapping without modifying SQL or FGA:

```sh
cd apps/knowledge-flow-backend
uv run python alembic/backfill/convert_corpus_owners.py
```

The JSON result contains `applied: false` and the complete folder-to-team mapping.
The tool reads explicit owner tuples through the existing paginated Read API.
It disables store creation and model publication, including when configuration
normally enables them. An unavailable/missing store fails explicitly.

Stop if the tool reports missing or multiple owners, SQL/JSON disagreement,
SQL/FGA disagreement, non-document folders or paths that collide after conversion.
Review the reported folder IDs; do not repair or delete data merely to pass.
No owner is changed if any folder fails verification.

## Configuration

No new configuration keys. Use the existing deployment configuration; the tool
locally disables OpenFGA store creation and schema publication.

## Upgrade

With writers still stopped and backups verified:

```sh
uv run python alembic/backfill/convert_corpus_owners.py --apply
```

This repeats verification, then updates SQL and its stored JSON owner field in
one transaction. The output reports `applied: true`. It adds no migration table,
queue or runtime repair mechanism. FGA tuples are untouched: remove obsolete
corpus grants only in the later cutover step, preserving source-root grants.

Do not rerun conversion blindly after applying it: the retained historical FGA
user owner and the converted SQL team owner intentionally differ at this point.
Do not restart old services against this intermediate state.

Before reopening the new knowledge-flow backend, inventory every machine account
that consumes the corpus and provision its explicit root grants: viewer for
reads, editor for source synchronization writes. The service_agent role alone
will no longer grant corpus reads, including for evaluation accounts. No change
to the evaluation application or its configuration is included here. Preserve
these machine grants when retiring historical human/document relations.

The label-read endpoints `/documents/labels`, `/documents/by-label` and
`/documents/by-label/{label}` now require `team_id` (use `personal` for the
caller's personal team). Deploy the regenerated frontend and runtime client
together with the backend. Agent label search uses the conversation team and
the union of selected folders/documents; foreign-team IDs never widen it.

The legacy folder-sharing endpoints are removed: `POST /tags/{id}/share`,
`DELETE /tags/{id}/share/{target_id}`, and `GET /tags/{id}/members`.
Human corpus access follows team membership; there is no replacement folder-sharing
API. Provision explicit machine root grants through the deployment's OpenFGA
administration procedure before reopening access.

## Validation

Compare the reported mapping with `SELECT tag_id, owner_id FROM tag` and verify
unchanged folder/document counts. An error before commit leaves SQL owners
unchanged; a lost connection around commit requires manual inspection of SQL.
There is no automatic inference that a failed connection means rollback.

## Rollback

Before reopening services, finish and verify the matching schema, runtime,
authorization and index cutover. Rolling back after conversion requires the
verified original SQL owners and matching old code/schema; an Alembic downgrade
alone cannot reconstruct whether an original owner was a user or a team.

## Tabular access

Tabular corpus requests now use authorized team folders instead of document-level
ReBAC listings. Without an explicit team, corpus discovery is scoped to the
caller's personal team; existing runtime tools supply their active team scope.
Service accounts require explicit source-root grants. Explicit owned conversation
attachment requests remain independent of corpus team permissions.

## Partial index updates

Rename and retrievability requests now return an explicit error if PostgreSQL
was updated but the vector-index operation failed, including an unsupported
operation. Metadata remains committed; the index may be partially updated.
Verify the stored metadata and affected index entries before manual repair.
There is no automatic rollback, cleanup or replay. Repeating a rename to the
already-saved name is a no-op and does not repair the index.

## Limitations

The complete SQL/FGA/index deployment sequence is still under implementation;
do not run this step independently and restart old knowledge-flow code.

Before upgrading the admission schema (`b2845a001005`), stop writers and finish or manually resolve every nonterminal ingestion task, including uploads whose start was not confirmed. The migration refuses otherwise: historical upload preparations have no safely inferable destination. It also refuses folders without a canonical owner, with an empty or slash-containing name, or whose stored parent path has no matching folder in the same team. Review these rows before upgrading; the migration does not infer a hierarchy. The new task `folder_id` is historical attribution and intentionally has no folder foreign key. Folder `deletion_task_id` belongs to the retained corpus row while cleanup is pending or failed; successful cleanup removes the row, while independent task history remains. Downgrade refuses outstanding deletion claims. The full deletion/migration cutover is still under implementation; this note is not a deployment-ready runbook.

Corpus deletion tasks cannot be cancelled through the UI or the task API (`HTTP 409`). A failed cleanup remains visible as a failed task; Fred does not restore artifacts already deleted.

## Folder rename contract

The existing `PUT /tags/{id}` now renames a folder and all descendant paths in one transaction when the parent path is retained. Clients should omit `path` when renaming by folder ID; omitting `item_ids` retains document membership. The UI sends one mutation and no descendant updates or membership snapshot. Folder IDs, source cursors and document memberships are preserved. Name collisions return HTTP 409 without a partial rename. Refresh the frontend as part of the coordinated cutover.


## Integration with name-conflict imports

The unpublished corpus migrations now follow knowledge-flow revision
`c3a71f5e0d48` from swift. Apply the single Alembic chain; no merge revision or
manual stamping is needed. The document-name index is retained alongside scalar
folder membership. Metadata conversion reads bounded pages and closes each query
before schema changes. The folder-path uniqueness expression preserves the same
NULL/empty-root semantics on PostgreSQL and SQLite.

Replacement imports retain the existing document ID in its single folder. An
active target rejects the whole backend request before any shared write. If a
confirmed replacement target disappears before planning or preparation, that file
fails explicitly: refresh the folder and start a new import. No automatic
recreation, resubmission or partial cleanup is introduced. This integration does
not complete the coordinated deployment runbook described above.
