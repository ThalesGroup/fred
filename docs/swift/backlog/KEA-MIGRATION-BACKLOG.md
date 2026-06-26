# Kea→Swift Migration Backlog

Epic: **MIGR-00** — Kea→Swift production cutover

This backlog tracks the workstreams needed to cut over from Kea (production) to
Swift (new architecture). Owner of each sub-item = the person doing the work.
Set `owner:` in `id-legend.yaml` when a ticket is picked up.

> **Operational source of truth:** [`ops/KEA_SWIFT_CUTOVER.md`](../ops/KEA_SWIFT_CUTOVER.md)
>
> **Detailed runbook:** [`ops/MIGRATION-CASTLE-TO-S3NS.html`](../ops/MIGRATION-CASTLE-TO-S3NS.html)
> (full procedure, organised by the four topics below — §1.1 identity · §1.4 data ·
> §1.2/§1.3 metadata · §1.5 products). This backlog holds the authoritative topic definitions.

---

## Migration model — vocabulary & order (READ FIRST — shared language)

Every migration discussion (chat, RFC, standup) uses **exactly these four topics**. They differ
in how they move and who owns them. Do not blur them.

| Topic | What it is | How it moves | Owner / tracked as |
| --- | --- | --- | --- |
| **identity** | Keycloak realm `app`: **users** (the `sub`) + **groups**. The IDs everything else points at. | Keycloak-native export→import, **out-of-band**, **IDs preserved**, merged into the pre-existing target realm. **Not in the export zip.** | platform/ops — **MIGR-04** |
| **data** | Raw document **binaries** in MinIO (`*-documents/<document_uid>/input/…`). Irreplaceable. | `mc mirror`, **keys verbatim**, two-hop via the laptop. No key rewriting. | **MIGR-06** |
| **metadata** | Structured records: Postgres rows (`tag, metadata, resource, mcp-server, teammetadata, users, agent`) **+ OpenFGA tuples**. | The **export `.zip`** → import (this is the import service). | **MIGR-02** (transform) + **MIGR-05** (import service) |
| **products** | Derived, **reconstructable-from-data** artifacts: OpenSearch embeddings, processed markdown/media, tabular parquet. | **Not transported** — rebuilt on the target (re-vectorize). | **MIGR-07** |

**Fixed order** (identity must precede everything because metadata tuples reference identity IDs):

```
0. Freeze source (read-only) for a consistent capture
1. identity   — Keycloak export→import, IDs preserved          (MIGR-04)
2. data       — mc mirror the buckets, key-for-key             (MIGR-06)
3. metadata   — export zip → import (Postgres + OpenFGA)       (MIGR-02 + MIGR-05)
4. products   — re-vectorize on the target                     (MIGR-07)
5. verify + cutover; keep source as rollback
```

**Two runs, two ID disciplines:**
- **kea → kea** (castle → s3ns, the **first** run): same schema, same names both ends
  (DB `fred_kea`, store `kea`, buckets `kea-*`, index `kea-vector-index-mistral`, realm `app`).
  **No transformation** — a faithful mirror.
- **kea → swift** (later): identity & data assumptions hold unchanged; only **names map**
  (store `kea`→`fred`, buckets `kea-*`→unprefixed, index `kea-…`→`vector-index-mistral`).
  The **metadata transform** (agent `payload_json`→`agent_instance`, per-user personal teams,
  UUID-only user-tuple filter) is swift-specific — see [`PLATFORM-IMPORT-RFC`](../rfc/PLATFORM-IMPORT-RFC.md).

**Two ID shapes — never conflate:**
- **`document_uid`** = 32-hex (`3ac3729e2152447081df3717ce338ffe`). **The MinIO folder name.**
  The *only* join between a binary and the rest of the system:
  MinIO folder ⟷ `metadata.document_uid` ⟷ OpenFGA `document:<document_uid>`.
- **`tag_id` / `team_id` / `agent_id` / `resource_id`** = dashed UUID. **Never appear in MinIO
  paths** — they live only in metadata. A document's tag/team comes 100% from metadata, never
  from the object path.

**Identity sub-facts (settled):**
- A Keycloak **group id = the team id = `teammetadata.id` = OpenFGA `team:<groupid>`**. Preserving
  group IDs is as critical as preserving user `sub`.
- **Team membership is NOT stored in OpenFGA** — it is derived from Keycloak group claims at
  request time. Membership therefore travels entirely with the realm; there are **no `user→team`
  tuples to import**.

---

## §0 Platform prerequisite — identity bootstrap (MIGR-04)

Must be completed and verified **before** any application data (Postgres `fred_kea`,
OpenFGA tuples) is imported into a target environment. Owned by platform/ops.

- [ ] **MIGR-04** — Bootstrap the target (S3NS) Keycloak by exporting on-prem users **with
  their `id` (UUID)** and importing them so each user's `sub` is preserved across environments.
  — *Fred keys all ownership and OpenFGA tuples on the Keycloak `sub`; a fresh Keycloak mints
  new UUIDs and orphans every user. SSO brokering alone preserves nothing.*
  — owner: platform/ops (Sébastien)
  — runbook: [`ops/KEYCLOAK-IDENTITY-BOOTSTRAP-S3NS.md`](../ops/KEYCLOAK-IDENTITY-BOOTSTRAP-S3NS.md)
  — acceptance: one real user logs into S3NS via SSO and their token `sub` equals their on-prem UUID
  — note: the application team rehearses the data migration locally with a **single shared
  Keycloak** (kea + swift), which faithfully models the post-bootstrap state; it does not test
  the bootstrap itself, which is why this item is owned by platform/ops.

---

## §0bis Platform import service (MIGR-05)

Rock-solid swift-side **import** counterpart to kea's throwaway export. Temporal-backed,
observable via the task/event stream, with an admin progress UI. Scope confirmed:
**config graph only** (agents, prompts/resources, tags, document metadata, MCP, team/users,
OpenFGA tuples), **fresh target only** (refuse if populated). Document blobs/vectors and
conversations are out of scope (re-ingest separately). RFC: [`PLATFORM-IMPORT-RFC`](../rfc/PLATFORM-IMPORT-RFC.md).

> **WIP status (start from fresh branches).** Done on the current branch: `migration/agent_map.py`
> (+tests) and the `/admin/migration` UI shell. Not done: the whole backend service (05.01–05.05,07).
> Validation path: **export from kea first, then import with swift.** The kea export may still be
> incomplete — verify against the §3 bundle contract; export gaps are kea's to fix. Governing
> principle: **dumb export / smart import** (see RFC "Canonical contract").

- [ ] **MIGR-05.01** — Bundle reader + manifest/schema validation (`format_version 1`)
- [ ] **MIGR-05.02** — `platform_import` Temporal workflow: validate → preflight → restore_relational → restore_agents → restore_openfga → verify
- [ ] **MIGR-05.03** — Agent transform: kea `payload_json`/`class_path` → swift `agent_instance` (+ catalog mapping table) — *main correctness risk*
- [ ] **MIGR-05.04** — OpenFGA tuple restore with identity/team validation + personal-team reconciliation
- [ ] **MIGR-05.05** — `MigrationDetail` task-event variant (matches frontend `MigrationTaskEvent`) + control-plane SSE wiring
- [x] **MIGR-05.06** — Admin UI `/admin/migration` import page (upload zip → launch → task-atom progress, admin-only) — *UI shell done; backend POST pending*
- [ ] **MIGR-05.07** — Stage reconciliation (dumb-export/smart-import): on restore, reset each doc's
  `VECTORIZED`/`SQL_INDEXED` → `NOT_STARTED`, conditionally reset `PREVIEW_READY`; consumed by MIGR-07
  re-vectorize. *Inert without the MIGR-07 trigger — two ends of one flow.*
  — RFC: [`PLATFORM-IMPORT-RFC`](../rfc/PLATFORM-IMPORT-RFC.md) "Canonical contract"
  — depends on: MIGR-04 (identity bootstrap), reuses TASK-EVENT-STREAM task/event infra

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

- [ ] **MIGR-07.01** — `list_documents_in_scope` activity (metadata query by tag_ids/library/document_uids/source_tag)
- [ ] **MIGR-07.02** — `RevectorizeCorpusWorkflow` + `RevectorizeDocument` workflows (batch fan-out, reuse `output_process`); register in scheduler worker
- [ ] **MIGR-07.03** — Wire the `/corpus/revectorize` stub to start the workflow + `task_service.start`; incremental/full/force semantics
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

- [ ] **MIGR-02.02** — Backfill script: migrate data from `agent` → `agent_instance`, then drop `agent`
  — *`agent` table is the Kea model; Swift uses `agent_instance` — production data must be migrated before cutover*

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

- [ ] **MIGR-03.03** — Source citation in chat — display source references alongside agent responses
  — *Kea showed which documents/sources were used in the response*

---

## Progress

| Workstream | Total | Done | Remaining |
| ---------- | ----- | ---- | --------- |
| MIGR-04 Identity (Keycloak bootstrap, IDs preserved) | 1 | 0 | 1 |
| MIGR-06 Data (MinIO mc mirror) | 3 | 0 | 3 |
| MIGR-05 Metadata — platform import service | 7 | 1 | 6 |
| MIGR-07 Products (re-vectorization) | 4 | 0 | 4 |
| MIGR-01 Cherry-picks | 15 (13 needed + 2 good-to-have) | 9 | 6 |
| MIGR-02 DB migration | 4 (2 required + 2 optional) | 0 | 4 |
| MIGR-03 Feature parity | 3 | 0 | 3 |
