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
| identity | MIGR-04 | platform/ops | Preserve Keycloak user `sub` before any application import. Team IDs are no longer Keycloak group IDs — see the migration note below. |
| data | MIGR-06 | application migration | Mirror MinIO buckets key-for-key; never rewrite `document_uid` paths. |
| metadata | MIGR-02 + MIGR-05 | application migration | Restore the config graph from the export zip into a fresh target only. |
| products | MIGR-07 | application migration | Rebuild embeddings and other derived artifacts on the target. |

## Non-Negotiables

- Keycloak user IDs (`sub`) are preserved, not remapped.
- Teams are not Keycloak groups (AUTHZ-05 review item 9, `platform/REBAC.md`,
  `FRED-AUTHORIZATION-TARGET-MODEL-RFC.md` Part 6): a team is a `team_metadata`
  row plus explicit OpenFGA relation tuples (`team_admin`/`team_editor`/
  `team_analyst`/`team_member`). See the migration note below — the previous
  "preserve the Keycloak group ID as the team ID" rule no longer applies.
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

## Migration Note — Teams Are No Longer Keycloak Groups

AUTHZ-05 review item 9 (2026-07-10, `FRED-AUTHORIZATION-TARGET-MODEL-RFC.md` Part 6,
`platform/REBAC.md`) decoupled teams from Keycloak entirely: a team is now a
`team_metadata` row (independently generated `uuid4().hex` id, plus `name`) with
membership as explicit OpenFGA relation tuples (`team_admin`/`team_editor`/
`team_analyst`/`team_member`) — no Keycloak group backs it, and there is no group ID to
preserve as the team ID. This revamps how MIGR-04/MIGR-02 must handle teams: user
identity migration (`sub` preservation) is unaffected, but team migration is now "create
a `team_metadata` row per source team, then write the equivalent membership tuples
directly" rather than "preserve the group ID." The concrete import mechanics for this
(source team enumeration, id/name mapping, tuple-writing order) are not yet designed —
track as a follow-up before this document's team-related steps are treated as
actionable.

## Current Implementation State

| Area | Current state |
| --- | --- |
| Identity | Runbook exists in `KEYCLOAK-IDENTITY-BOOTSTRAP-S3NS.md`; platform-owned and not implemented by Swift code. Note: swift ignores Keycloak realm roles — kea platform admins must be re-granted `platform_admin` explicitly (bundle `users.json` or bootstrap). |
| Data mirror | Procedure tracked in MIGR-06; no Swift service is expected for the `mc mirror` itself. |
| Metadata import backend | Implemented (2026-07-24): `POST /control-plane/v1/import-export/import` (`control_plane_backend/import_export/`), atomic transaction + task events. Kea path covers agents (incl. prompt/tuning transfer), chat-contexts → personal prompts, tags/metadata, teammetadata, and OpenFGA tuple restore with role transformation (`owner→team_admin+team_editor`, `manager→team_editor`, `member→team_member`). Validated against a real kea dump (2026-07-22). |
| Metadata import UI | **Platform data** admin page, wired to the live backend (MIGR-05.06). |
| Agent mapping | `control_plane_backend/import_export/agent_map.py` and tests exist. Gaps must block real cutover — run a prod template inventory before cutover. |
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

- a target Keycloak user gets a new UUID;
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
