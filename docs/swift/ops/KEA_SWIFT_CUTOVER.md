# Kea to Swift Cutover

**Status**: Operational source of truth for MIGR-00 planning.

**Backlog**: [`../backlog/KEA-MIGRATION-BACKLOG.md`](../backlog/KEA-MIGRATION-BACKLOG.md)

This document keeps the production cutover model small and explicit. The
implementation RFCs stay focused on the pieces that are not built yet.

## Fixed Order

Run the migration in this order:

1. Freeze the source for a consistent capture.
2. Mirror document binaries.
3. Import metadata (identity is resolved by username inline, see below).
4. Rebuild derived products.
5. Verify, cut over users, and keep the source as rollback.

Do not reorder these steps. Metadata joins to document binaries by
`document_uid`, and product rebuilds depend on imported metadata plus
mirrored `output/` artifacts.

## Three Topics

| Topic | Tracked as | Owner | Rule |
| --- | --- | --- | --- |
| data | MIGR-06 | application migration | Mirror MinIO buckets key-for-key; never rewrite `document_uid` paths. |
| metadata | MIGR-02 + MIGR-05 | application migration | Restore the config graph from the export zip into a fresh target only; resolves identity by username inline (no separate identity step — see below). |
| products | MIGR-07 | application migration | Rebuild embeddings and other derived artifacts on the target. |

## Identity — resolved by username, not preserved

At the start of a migration run, target Keycloak holds **only the root admin** —
there is no out-of-band identity bootstrap step and no expectation that a
user's Keycloak `sub` carries over from the source. A fresh Keycloak mints a
new `sub` for each person the first time they log in via SSO.

The metadata import resolves identity by **username**, using `kea_sub →
username` from the bundle and `username → swift_sub` from the live target
Keycloak (`kea_reconciliation.py`). Three outcomes per user: `MATCHED` (same
`sub` both sides), `RELINKED` (found under a different `swift_sub` — that
`sub` is used everywhere), `PENDING` (username not yet in target Keycloak,
i.e. before their first login). A `PENDING` user never blocks the rest of the
import: everything keyed on their identity is deferred, never written under
the old kea `sub`. Re-running the same import after their first login
resolves them to `MATCHED`/`RELINKED` and completes the deferred data —
convergent, no duplicates. See `CONTROL-PLANE-PRODUCT-CONTRACT.md` for the
contract detail.

## Non-Negotiables

- No Keycloak `sub` from the kea export is ever written as a Swift identity;
  identity is resolved by username as described above.
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
preserve as the team ID. This revamps how MIGR-02 must handle teams: team migration is
now "create a `team_metadata` row per source team, then write the equivalent membership
tuples directly" rather than "preserve the group ID." The concrete import mechanics for this
(source team enumeration, id/name mapping, tuple-writing order) are not yet designed —
track as a follow-up before this document's team-related steps are treated as
actionable.

## Current Implementation State

| Area | Current state |
| --- | --- |
| Identity | Implemented inline in the metadata import (`kea_reconciliation.py`): username-based resolution, `MATCHED`/`RELINKED`/`PENDING`. Platform roles come from the bundled realm export's `realmRoles` when a full export is provided (MIGR-05.16); otherwise `users.json`/bootstrap is the fallback channel. |
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

- an identity write bypasses username resolution — i.e. a raw, unresolved kea
  `sub` is persisted somewhere without going through `resolve_user_sub`/
  `KeaUserResolver` first (a `MATCHED` user's *resolved* `swift_sub`
  legitimately equals their kea `sub` — that is the expected, correct case,
  not this);
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
