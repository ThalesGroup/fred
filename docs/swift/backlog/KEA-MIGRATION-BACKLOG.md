# Kea→Swift Migration Backlog

Epic: **MIGR-00** — Kea→Swift production cutover

This backlog tracks the workstreams needed to cut over from Kea (production) to
Swift (new architecture). Owner of each sub-item = the person doing the work.
Set `owner:` in `id-legend.yaml` when a ticket is picked up.

> **Operational source of truth:** [`ops/KEA_SWIFT_CUTOVER.md`](../ops/KEA_SWIFT_CUTOVER.md)
>
> This backlog holds the authoritative topic definitions.

---

## Migration model — vocabulary & order (READ FIRST — shared language)

Every migration discussion (chat, RFC, standup) uses **exactly these three topics**. They differ
in how they move and who owns them. Do not blur them.

Identity is **not** a separate topic: at the start of a run, target Keycloak holds only the
root admin, and there is no out-of-band step that pre-seeds it. Identity is resolved by
**username** inline inside the metadata import (`kea_reconciliation.py`): `kea_sub → username`
from the bundle, `username → swift_sub` from the live target Keycloak. Three outcomes —
`MATCHED` (same `sub`), `RELINKED` (different `swift_sub` — that one is used everywhere),
`PENDING` (username not yet in target Keycloak). A `PENDING` user never blocks the rest of the
import; everything keyed on their identity is deferred and completed by re-running the same
import after their first login. No kea `sub` is ever written as a Swift identity. See
`CONTROL-PLANE-PRODUCT-CONTRACT.md` for the live contract.

| Topic | What it is | How it moves | Owner / tracked as |
| --- | --- | --- | --- |
| **data** | Raw document **binaries** in MinIO (`*-documents/<document_uid>/input/…`). Irreplaceable. | `mc mirror`, **keys verbatim**, two-hop via the laptop. No key rewriting. | **MIGR-06** |
| **metadata** | Structured records: Postgres rows (`tag, metadata, resource, mcp-server, teammetadata, users, agent`) **+ OpenFGA tuples**. Identity resolution (above) runs inline as part of this phase. | The **export `.zip`** → import (this is the import service). | **MIGR-02** (transform) + **MIGR-05** (import service) |
| **products** | Derived, **reconstructable-from-data** artifacts: OpenSearch embeddings, processed markdown/media, tabular parquet. | **Not transported** — rebuilt on the target (re-vectorize). | **MIGR-07** |

**Fixed order:**

```
0. Freeze source (read-only) for a consistent capture
1. data       — mc mirror the buckets, key-for-key                          (MIGR-06)
2. metadata   — export zip → import; identity resolved by username inline  (MIGR-02 + MIGR-05)
3. products   — re-vectorize on the target                                  (MIGR-07)
4. verify + cutover; keep source as rollback
   (PENDING users complete their data on first login + re-running the same import)
```

**Two runs, two ID disciplines:**
- **kea → kea** (castle → s3ns, the **first** run): same schema, same names both ends
  (DB `fred_kea`, store `kea`, index `kea-vector-index-mistral`, realm `app`).
  **No transformation** — a faithful mirror.
- **kea → swift** (later): identity & data assumptions hold unchanged; only **names map**
  (store `kea`→`fred`, index `kea-…`→`vector-index-mistral`).
  The **metadata transform** (agent `payload_json`→`agent_instance`, per-user personal teams,
  UUID-only user-tuple filter) is swift-specific — see [`PLATFORM-IMPORT-RFC`](../rfc/PLATFORM-IMPORT-RFC.md).

**Correction, 2026-07-27 — bucket naming was wrong above.** The `kea-*`→unprefixed
bucket-name mapping stated in earlier versions of this section was a **local rehearsal
artifact** (the docker-compose test stack prefixes its own kea-simulation buckets with
`kea-` to keep them apart from the swift-simulation ones sharing the same SeaweedFS
instance), not the real convention. Confirmed today against the actual GCS layout:
- **kea/castle** (both the old MinIO deployment and the new GCS one — identical):
  bucket names carry **no prefix at all** — `knowledge-flow-content-documents`,
  `knowledge-flow-content-objects`, `control-plane-content-objects`, `filesystem`, `app-bucket`.
- **swift/S3NS**: bucket names carry whatever prefix the Helm chart injects at deploy
  time — an operator choice, not an application constant. TP-S3NS today uses
  `prism-swift-` (e.g. `prism-swift-knowledge-flow-documents`,
  `prism-swift-filesystem`) — the same prefix already used in the integration
  environment, added by hand in the Helm values.

  Nothing in the application code assumes either naming — MIGR-06 (`mc mirror`) is a
  pure ops step external to the Fred codebase, so this is a documentation correction,
  not a code fix. When mapping source→target buckets for a real mirror, read the
  actual bucket name from each environment's own Helm values/console rather than
  assuming a fixed prefix pattern on either side.

**Two ID shapes — never conflate:**
- **`document_uid`** = 32-hex (`3ac3729e2152447081df3717ce338ffe`). **The MinIO folder name.**
  The *only* join between a binary and the rest of the system:
  MinIO folder ⟷ `metadata.document_uid` ⟷ OpenFGA `document:<document_uid>`.
- **`tag_id` / `team_id` / `agent_id` / `resource_id`** = dashed UUID. **Never appear in MinIO
  paths** — they live only in metadata. A document's tag/team comes 100% from metadata, never
  from the object path.

**Identity sub-facts (settled):**
- The Keycloak `sub` is **not** stable across environments and is never assumed preserved.
  Identity is resolved by username inline in the metadata import — see the model note above.
- **Migration note — teams are no longer Keycloak groups (2026-07-10).** This section previously
  asserted "a Keycloak group id = the team id" and "membership derives from Keycloak group claims,
  no `user→team` tuples to import." Both are now false for the swift target: AUTHZ-05 review item 9
  (`FRED-AUTHORIZATION-TARGET-MODEL-RFC.md` Part 6, `platform/REBAC.md`) made a team a
  `team_metadata` row (independently generated id, plus a required `name` column) with membership
  as **explicit** OpenFGA relation tuples (`team_admin`/`team_editor`/`team_analyst`/`team_member`)
  — no Keycloak group backs it, and swift's `team_metadata.id` can still reuse a kea team's old
  group-id string (opaque to swift), but the **metadata** topic (MIGR-02/MIGR-05) must now write
  `user→team` tuples explicitly for every migrated team — see `PLATFORM-IMPORT-RFC.md` §2/§4 for
  the corrected plan. Concrete import
  mechanics (source-team enumeration, tuple-writing order) are not yet designed.

---

## §0bis Platform import service (MIGR-05)

Full contract: [`PLATFORM-IMPORT-RFC.md`](../rfc/PLATFORM-IMPORT-RFC.md) — swift-native path
shipped + hardened; kea-import path (this checklist's `[ ]` items) deferred, tracked below.

- [x] **MIGR-05.01** — Bundle reader + manifest parse (`format_version 1`, kea + swift formats) — `import_export/bundle.py`
- [x] **MIGR-05.02** — Atomic import service (FastAPI `BackgroundTask` + single SQLAlchemy transaction; **not** Temporal): validate manifest → import agents → tags → metadata, all-or-nothing rollback, idempotent by PK — `import_export/importer.py` + `api.py`. *(Temporal design preserved in RFC §5 for future scale; fresh-target preflight + verify superseded by idempotent-by-PK + reset.)*
- [x] **MIGR-05.03** — Agent transform: kea `payload_json`/`class_path` → swift `agent_instance` (+ `KEA_TO_SWIFT_TEMPLATE` catalog; IGNORED skipped, GAP warned) — `import_export/agent_map.py` (+tests)
- [x] **MIGR-05.04** — OpenFGA tuple restore (2026-07-24, #1954) — `importer.py::transform_kea_tuples`,
  replacing the abandoned ops bulk-copy plan (Option A would have written kea relation names the
  swift model rejects — 63% of the tuples in the validated 2026-07-22 kea dump). Role mapping
  (approved): `owner→team_admin+team_editor`, `manager→team_editor`, `member→team_member`;
  `team_analyst` never synthesized. Dropped + counted: kea shared `team:personal` tuples (swift
  self-heals `personal-{uid}`), `resource#parent` (resources become prompt rows), non-UUID user
  subjects. Residual: no per-identity Keycloak existence check (tuples for unknown subs are inert).
- [x] **MIGR-05.05** — `MigrationTaskEvent` populated (`step`/`progress`/`MigrationDetail`) + control-plane wired into frontend task rehydration & SSE sources (tasks survive reload)
- [x] **MIGR-05.06** — Admin UI import page (upload zip → launch → task-atom progress, admin-only) — *fully wired to the live backend; page renamed **Platform data***
- [x] **MIGR-05.07** — Stage reconciliation: reset each restored document's `VECTORIZED`/
  `SQL_INDEXED` → `NOT_STARTED` (never transported), `PREVIEW_READY` untouched. Closed by
  MIGR-05.13 (`importer.py::_reset_transported_stages`) — the metadata-import phase is shared code,
  not swift-only, so this applies to both the swift-native and kea-import paths. *Still inert until
  MIGR-07's re-vectorize trigger actually consumes the reset — two ends of one flow.*
  — RFC: [`PLATFORM-IMPORT-RFC`](../rfc/PLATFORM-IMPORT-RFC.md) §5
- [x] **MIGR-05.08** — Tags + document-metadata import phases (atomic, shared generic loop) — `import_export/importer.py`; new `fred_core/documents/tag_models.py` `TagRow`
- [x] **MIGR-05.09** — Swift-native **export** (`GET /import-export/export`) + re-import branch (`source_platform=swift`, bypasses `agent_map`) — `import_export/exporter.py`
- [x] **MIGR-05.10** — Atomic **reset** (`POST /import-export/reset`) — wipes agents+tags+metadata in one transaction; enables export → reset → import test cycles (object store / Keycloak / OpenFGA untouched)
- [x] **MIGR-05.11** — Agent prompt transfer (2026-07-24, #1954). Implemented differently from the
  original sketch: the kea prompt (`system_prompt_template` v2 / `prompts.system` v1, from
  `payload_json.tuning.fields[].default`) is written to `tuning.values["prompts.system"]` — the
  key the runtime actually overlays onto the template's system prompt
  (`fred_runtime/app/agent_app.py`). `prompt_refs_json` is left unset: it has no consumer in the
  codebase, and kea agent prompts were never library entries. `role`/`description`/`tags`/
  `created_by` also transfer; v1 secondary per-node prompts are warned (no swift field).
  — RFC: [`PLATFORM-IMPORT-RFC`](../rfc/PLATFORM-IMPORT-RFC.md) §8
- [x] **MIGR-05.12** — Platform-data stats dashboard (`GET /import-export/stats`): teams, members by
  role, agents, prompts; personal spaces (`personal-*`) aggregated into one row — `import_export/stats.py`
- [x] **MIGR-05.13** — Manifest contract hardening: `SnapshotManifest` → Pydantic + enforced
  `format_version`/`users_schema_version` (reject unknown, no silent default) — `bundle.py`; honest
  `content_keys` (populated on export, surfaced as a single count-warning on import — not a
  per-document content-store probe, that's a future MIGR-06-side improvement) instead of an
  always-`[]` placeholder — `exporter.py`/`importer.py`. Also closed MIGR-05.07 (stage
  reconciliation) as a side effect, since it touched the same shared metadata-import phase. Tests:
  `tests/test_import_export_manifest.py` (5 new). — RFC:
  [`PLATFORM-IMPORT-RFC`](../rfc/PLATFORM-IMPORT-RFC.md) §4–§5
- [x] **MIGR-05.14** — Kea bundle compatibility fixes (2026-07-24, #1954), found by running a real
  kea dump (2026-07-22) through the importer: (a) kea manifests predate `users_schema_version` →
  defaulted to 1 for `source_platform != "swift"` only (RFC §4 amended); (b) the team table file is
  `teammetadata.jsonl` on the kea path (main's `EXPORT_TABLES` name) vs `team_metadata.jsonl`
  (swift-native) — the importer now asks for the right file per producer; (c) legacy
  `payload_json.type == "leader"` agent rows skipped. Tests: `tests/test_import_export_kea_bundle.py`.
- [x] **MIGR-05.15** — Chat contexts → personal prompts (2026-07-24, #1954, decision: personal
  space only). Kea `resource` rows (`resource_type="chat-context"`) become `prompt` rows in
  `personal-{author}`; YAML front-matter stripped (body only); `prompt_id` = kea `resource_id`
  (idempotent); `(team_id, name)` collisions suffixed; kinds `prompt`/`template` skipped with a
  warning; kea library tags (`chat-context`/`prompt`/`template`) filtered from the tag phase.
  — RFC: [`PLATFORM-IMPORT-RFC`](../rfc/PLATFORM-IMPORT-RFC.md) §8

- [x] **MIGR-05.16** — Teams & platform roles from the bundled Keycloak realm export
  (2026-07-24, #1954). Every tuple-referenced team now gets a swift `teammetadata` row: name ←
  `keycloak/realm.json` groups (kea's only team-name store), customization merged from the kea
  row when present; no realm in the bundle → named by id + warning. When the realm export is a
  FULL one (`kc export --users`), per-user `realmRoles` re-provision platform roles
  (`admin→platform_admin`, `viewer→platform_observer`, `editor` dropped + warned); a
  partial-export carries no users → `users.json`/bootstrap remains the channel. Ops fallback for
  both: SQL on the Keycloak DB (`keycloak_group`, `user_role_mapping`×`keycloak_role`).

- [x] **MIGR-05.18** — Standalone `realm_file` upload + teardown (2026-07-24, cutover
  hardening; simplified 2026-07-27). `POST /import` gains an optional second multipart field
  `realm_file` — a Keycloak realm export supplied independently of the zip, taking precedence
  over the zip's own `keycloak/realm.json` when present. Unblocks cutover regardless of the
  kea-side `exportClients` 403 (§0bis "Open" item below is now a nice-to-have, not a blocker).
  `POST /reset-rebac` (distinct endpoint/button from `/reset`, which keeps its narrow
  dev/test-cycle scope unchanged): test-only teardown back to bootstrap-only state — OpenFGA
  (`delete_all_relations_of_reference` per non-preserved user, per team), Postgres
  (`agent_instance`, `tag`, `document_metadata`, `team_metadata`, `prompt` in one transaction).
  Preserves `platformbootstrap.completed_by` ∪ the calling operator's identity. **Never touches
  Keycloak** — Fred does not own Keycloak identity lifecycle (identity is resolved by username
  against a live target Keycloak, never created/destroyed by this tooling, see
  `ops/KEA_SWIFT_CUTOVER.md`). `POST /reset-full` (which also deleted Keycloak users) is removed
  as of 2026-07-27 — it was cutover-day recovery scaffolding that contradicted this design; its
  UI button moves from the general **Platform data** page into the kea-specific
  `KeaMigrationPage.tsx` (deleted together with that page after cutover) as the single **Teardown**
  affordance. Migration-task concurrency guard (`/import` and `/reset-rebac` refuse to start while
  another migration task is active).
  — Contract: [`CONTROL-PLANE-PRODUCT-CONTRACT.md`](../design/CONTROL-PLANE-PRODUCT-CONTRACT.md) §27, §31

- [ ] **MIGR-05.17** — **User-state migration — future task, deliberately out of #1954 (which
  focuses on teams).** Still unowned on the application side:
  (a) `users.jsonl` (GCU-acceptance rows) is exported but never imported — decide re-prompt
  everyone on swift (current behaviour) vs adding a users-row import phase;
  (b) verify at cutover that platform-role re-provisioning actually happened — it is automatic
  only when the bundle's `realm.json` carries `users[]` (full export); a partial-export does not,
  and the fallback is `users.json` `platform_roles` or manual grants;
  (c) per-user/team storage counters — run knowledge-flow's
  `alembic/backfill/backfill_storage_usage.py` post-import (add to runbook).

**Open (cutover items — see RFC §8 follow-ups):**
- Kea-side realm-export 403: `manage-realm` alone does not satisfy `partial-export?exportClients=true`
  (needs `view-clients`, or export without clients). Must be fixed on the kea source before the
  prod dump, else teams arrive unnamed and platform roles must be provisioned via `users.json`.

---

## §0ter Data — document binaries (MIGR-06)

The **data** topic: mirror MinIO buckets **key-for-key** through the laptop bridge (no key
rewriting; team/tag reorganisation lives in metadata, never in object paths). ~25 GB.

- [ ] **MIGR-06.01** — Documented two-hop `mc mirror` procedure (source → encrypted laptop disk → target), buckets: `*-knowledge-flow-content-documents`, `*-knowledge-flow-content-objects`, `*-filesystem`
- [ ] **MIGR-06.02** — Integrity check: object-count reconciliation source vs target (per bucket / per `document_uid` prefix)
- [ ] **MIGR-06.03** — Encryption-at-rest of the bundle on the laptop during transit
  — note: banners live in the metadata zip, **not** in the data mirror
  — kea→swift delta: bucket names map (`kea-*` → unprefixed); keys (`document_uid/…`) unchanged

---

## §0quater Products — re-vectorization (MIGR-07)

The **products** topic: embeddings and other derived artifacts are **rebuilt on the target**,
not transported. Because `input/` **and** `output/` are mirrored together, only embeddings
(OpenSearch `*-vector-index-mistral`) must be regenerated. Design:
[`CORPUS-REVECTORIZE-RFC`](../rfc/CORPUS-REVECTORIZE-RFC.md) — redesign the **existing stubbed**
`/corpus/revectorize` endpoint onto a Temporal workflow over the existing `output_process` activity,
streaming progress via the fred-core task/event API (reuses `IngestionDetail`).

- [x] **MIGR-07.01** — `list_documents_in_scope` activity (metadata query by tag_ids/library/document_uids/source_tag)
- [x] **MIGR-07.02** — `RevectorizeCorpusWorkflow` + `RevectorizeDocument` workflows (batch fan-out, reuse `output_process`); register in scheduler worker
- [x] **MIGR-07.03** — Wire the `/corpus/revectorize` stub to start the workflow + `task_service.start`; incremental/full/force semantics
- [ ] **MIGR-07.04** — Migration UI "Rebuild embeddings" final step (reuse task atoms); reconcile vector `_count` vs metadata row count
  — kea→swift delta: same embedding model → vectors compatible; index name maps
  — RFC: [`CORPUS-REVECTORIZE-RFC`](../rfc/CORPUS-REVECTORIZE-RFC.md)

---

## §1 Cherry-picks and code adaptations (MIGR-01)

Commits or features from the Kea codebase that need to be cherry-picked or
re-implemented for Swift. For each item, note the source commit/PR and what
adaptation is needed (e.g. API contract change, dependency replacement).

Legend: **[needed]** = blocking for production cutover · **[good-to-have]** = quality / dev-experience

### Needed

- [ ] **MIGR-01.01** — Upload warning banner on document upload drawer and chat attachments
  — *SSI requirement: prevent accidental upload of sensitive files*
  — source: [#1597](https://github.com/ThalesGroup/fred/commit/34ea331a3) `34ea331` · [#1634](https://github.com/ThalesGroup/fred/commit/7b6320bc3) `7b6320b`
  — adaptation: check if chat attachment component exists in Swift; both commits may need to be applied

- [ ] **MIGR-01.02** — Fix GCU acceptation button on specific resolutions + placement fixes (delete agent button, add-member popover, select popover)
  — *GCU acceptance was broken on some screen sizes, reported in production*
  — source: [`4fc90cc`](https://github.com/ThalesGroup/fred/commit/4fc90cc8d)

- [ ] **MIGR-01.03** — Dockerfile base image bumps: Node + nginx
  — *CVE fixes requested by SSI on frontend image*
  — source:
    - [ ] [#1635](https://github.com/ThalesGroup/fred/commit/a41540422) `a414404`
    - [X] [#1647](https://github.com/ThalesGroup/fred/commit/38d4880ce) `38d4880`

- [ ] **MIGR-01.04** — Add `created_at` / `updated_at` timestamps to all ORM tables
  — *Required to verify production KPIs*
  — source: [#1612](https://github.com/ThalesGroup/fred/commit/e2be3fb7c) `e2be3fb`

- [ ] **MIGR-01.05** — Migrate to trunk-based development with unified release tag
  — *Rename main branch to `main`; single tag triggers a release*
  — source: [#1622](https://github.com/ThalesGroup/fred/commit/67916e113) `67916e1`

- [X] **MIGR-01.06** — Garbage-collect uploaded files after processing to prevent `/tmp` clogging
  — *Prevents disk exhaustion in the Temporal worker in production*
  — source: [#1605](https://github.com/ThalesGroup/fred/commit/ea048fe06) `ea048fe`

- [X] **MIGR-01.07** — Guard against `undefined` before calling `.toLowerCase()` in frontend
  — *Fixes a frontend crash reported by a user*
  — source: [#1611](https://github.com/ThalesGroup/fred/commit/026f21a6a) `026f21a`

- [X] **MIGR-01.08** — Fix broken link in team join-request email
  — *Wrong URL in the invite email*
  — source: [#1589](https://github.com/ThalesGroup/fred/commit/5dd8a8f4d) `5dd8a8f`

- [X] **MIGR-01.11** — Inherit `extraVolumes` and `extraVolumeMounts` in Helm hook Job
  — *Migration hook Jobs were missing volume mounts defined at chart level*
  — source: [#1659](https://github.com/ThalesGroup/fred/commit/7dce0561c) `7dce056`

- [X] **MIGR-01.12** — Add fast PDF processor
  — *New processor significantly reduces PDF ingestion time*
  — source: [#1626](https://github.com/ThalesGroup/fred/commit/3ab0af7a3) `3ab0af7`

- [X] **MIGR-01.13** — Mitigate knowledge-flow worker memory pressure during PDF medium-rich ingestion
  — *Prevents OOM crashes on large/rich PDFs in production*
  — source: [#1624](https://github.com/ThalesGroup/fred/commit/45db88821) `45db888`

- [X] **MIGR-01.14** — Cap concurrent uvicorn connections, configurable via Helm values and Makefiles
  — *Prevents connection overload; tunable per environment*
  — source: [#1627](https://github.com/ThalesGroup/fred/commit/688c4fa91) `688c4fa`

- [X] **MIGR-01.15** — Add custom `RetryPolicy` support for Temporal activities
  — *Allows per-activity retry tuning to avoid cascading failures*
  — source: [#1576](https://github.com/ThalesGroup/fred/commit/6550bb73d) `6550bb7`

### Good to have

- [ ] **MIGR-01.09** — Remove SCSS, migrate to pure CSS className syntax
  — *Removes old SCSS layer; project is now pure CSS*
  — source: [#1636](https://github.com/ThalesGroup/fred/commit/419b79554) `419b795`

- [X] **MIGR-01.10** — Fix company-managed CA certificate handling in local dev environment
  — *Required for developers working on Leap*
  — source: [#1620](https://github.com/ThalesGroup/fred/commit/403bf3aff) `403bf3a`

---

## §2 Postgres data/schema migration and backfill scripts for Fred tables(MIGR-02)

Schema diffs and backfill scripts for existing production data.
Each row represents one backfill script or migration step.

### Required

- [ ] **MIGR-02.01** — Cherry-pick `created_at` / `updated_at` timestamps on all ORM tables
  — *Prerequisite for KPI queries on production data*
  — depends on: MIGR-01.04 (same commit, must land first)

- [x] **MIGR-02.02** — Superseded (2026-07-24, #1954): the adopted cutover strategy is
  fresh-target export-zip → import, so the kea `agent` table never exists on the swift DB and
  there is nothing to backfill in place. The `agent` → `agent_instance` transform ships in the
  import service (MIGR-05.03 template mapping + MIGR-05.11 prompt/tuning transfer). Only relevant
  again if an in-place upgrade path is ever chosen.

### Optional

- [ ] **MIGR-02.03** — Backfill script: migrate conversations from `session` → `session_metadata`
  — *Table rename between Kea and Swift; existing sessions would be lost without this*

- [ ] **MIGR-02.04** — Handle `session_history` schema change
  — *Schema differs between Kea and Swift; assess: migrate in place, transform, or accept history loss*

---

## §3 Feature parity — Kea features missing in Swift (MIGR-03)

Features present in Kea production that are not yet in Swift.
For each item: assess whether to port as-is, adapt to Swift architecture, or drop
with a written rationale.

- [ ] **MIGR-03.01** — Session attachments — add document to a conversation directly
  — *Users could attach documents inline in a chat session in Kea*

- [ ] **MIGR-03.02** — Message feedback — leave a rating with 5 stars and a comment on a chat message
  — *Feedback feature was available in Kea; used for quality monitoring*

- [x] **MIGR-03.03** — Source citation in chat — display source references alongside agent responses
  — *Kea showed which documents/sources were used in the response*
  — Restored kea's inprocess `kf_vector_search` provider for the "search_documents"
    tool so it returns typed `VectorSearchHit` sources (Sources panel + `[N]`
    citations) instead of the remote-MCP plain-text path that dropped them.
  — Execution: branch `1883-fred-202-rgpd-ready-increment-ctrlp-12`. Touches
    `libs/fred-runtime/fred_runtime/integrations/kf_vector_search/`,
    `inprocess_toolkit_registry.py`, `mcp_catalog.yaml`, `deploy/charts/fred/values.yaml`.

---

## Progress

| Workstream | Total | Done | Remaining |
| ---------- | ----- | ---- | --------- |
| MIGR-06 Data (MinIO mc mirror) | 3 | 0 | 3 |
| MIGR-05 Metadata — platform import service | 17 | 16 | 1 (MIGR-05.17 users, see §0bis) |
| MIGR-07 Products (re-vectorization) | 4 | 3 | 1 |
| MIGR-01 Cherry-picks | 15 (13 needed + 2 good-to-have) | 9 | 6 |
| MIGR-02 DB migration | 4 (2 required + 2 optional) | 1 (02.02 superseded by MIGR-05) | 3 |
| MIGR-03 Feature parity | 3 | 1 | 2 |
