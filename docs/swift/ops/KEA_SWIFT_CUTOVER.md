# Kea to Swift Cutover

**Status**: Operational source of truth for MIGR-00 planning.

**Backlog**: [`../backlog/KEA-MIGRATION-BACKLOG.md`](../backlog/KEA-MIGRATION-BACKLOG.md)

**Detailed procedure**: [`MIGRATION-CASTLE-TO-S3NS.html`](MIGRATION-CASTLE-TO-S3NS.html)

This document keeps the production cutover model small and explicit. The
implementation RFCs stay focused on the pieces that are not built yet.

## Fixed Order

Run the migration in this order:

1. Freeze the source for a consistent capture.
2. Bootstrap identity on the target.
3. Mirror document binaries.
4. Import metadata.
5. Rebuild derived products.
6. Verify, cut over users, and keep the source as rollback.

Do not reorder these steps. Metadata references identity IDs, metadata joins to
document binaries by `document_uid`, and product rebuilds depend on imported
metadata plus mirrored `output/` artifacts.

## Four Topics

| Topic | Tracked as | Owner | Rule |
| --- | --- | --- | --- |
| identity | MIGR-04 | platform/ops | Preserve Keycloak user `sub` and group IDs before any application import. |
| data | MIGR-06 | application migration | Mirror MinIO buckets key-for-key; never rewrite `document_uid` paths. |
| metadata | MIGR-02 + MIGR-05 | application migration | Restore the config graph from the export zip into a fresh target only. |
| products | MIGR-07 | application migration | Rebuild embeddings and other derived artifacts on the target. |

## Non-Negotiables

- Keycloak user IDs and group IDs are preserved, not remapped.
- Team membership travels with Keycloak group claims, not OpenFGA tuples.
- `document_uid` is the only join between object storage, metadata rows, and
  OpenFGA document tuples.
- The data mirror runs before metadata import and mirrors both `input/` and
  `output/`.
- Metadata import is a smart import: it validates identities, maps agents, and
  resets vector/search processing stages to match target reality.
- Vectors are never transported. A migrated document is not search-ready until
  MIGR-07 completes.
- Conversations and message history are out of scope unless a separate confirmed
  migration item is created.

## Current Implementation State

| Area | Current state |
| --- | --- |
| Identity | Runbook exists in `KEYCLOAK-IDENTITY-BOOTSTRAP-S3NS.md`; platform-owned and not implemented by Swift code. |
| Data mirror | Procedure tracked in MIGR-06; no Swift service is expected for the `mc mirror` itself. |
| Metadata import backend | Not implemented. `POST /control-plane/v1/migration/import`, workflow, activities, OpenFGA restore, and control-plane task events remain MIGR-05 work. |
| Metadata import UI | `/admin/migration` shell exists and posts to the planned backend endpoint. It will show an error until the backend lands. |
| Agent mapping | `control_plane_backend/migration/agent_map.py` and tests exist. Gaps must block real cutover. |
| Task events | Shared task UI and SSE routing can route `migration` tasks to control-plane. |
| Product revectorization | `/corpus/revectorize` exists, but the service is still a mock task. The Temporal workflow is MIGR-07 work. |

## Open Implementation RFCs

| RFC | Scope | Keep / amend rule |
| --- | --- | --- |
| [`PLATFORM-IMPORT-RFC.md`](../rfc/PLATFORM-IMPORT-RFC.md) | Metadata import service, bundle contract, agent mapping, stage reconciliation. | Amend for MIGR-05 backend decisions. Do not create another metadata-import RFC. |
| [`CORPUS-REVECTORIZE-RFC.md`](../rfc/CORPUS-REVECTORIZE-RFC.md) | Product rebuild workflow over existing output processing. | Amend for MIGR-07 workflow decisions. Do not create another revectorization RFC. |
| [`TASK-EVENT-STREAM-RFC.md`](../rfc/TASK-EVENT-STREAM-RFC.md) | Generic task/event infrastructure used by import, ingestion, evaluation, and lifecycle tasks. | Amend only for shared task semantics, not migration-specific business order. |

## Stop Conditions

Stop the cutover if any of these are true:

- a target Keycloak user or group gets a new UUID;
- metadata import sees identities, teams, documents, or agent templates it cannot
  validate or map;
- the target already contains data that violates the fresh-target import policy;
- mirrored object counts do not reconcile;
- imported documents have `VECTORIZED` or `SQL_INDEXED` marked done before
  revectorization has rebuilt the target index;
- RAG/search validation fails after revectorization.

## Where To Update

- Update the backlog for sequencing, ownership, and acceptance checklist changes.
- Update `PLATFORM-IMPORT-RFC.md` for metadata import behavior.
- Update `CORPUS-REVECTORIZE-RFC.md` for product rebuild behavior.
- Update the detailed HTML runbook for concrete operator commands.
- Do not add a new RFC for the fixed four-topic order; amend this document and
  the backlog instead.
