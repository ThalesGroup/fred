# RFC — Platform Import service (kea→swift configuration restore)

**ID:** MIGR-05 · **Status:** draft (awaiting developer confirmation)
**Owner:** Dimitri · **Surface:** control-plane-backend + frontend
**Extends:** [`TASK-EVENT-STREAM-RFC.md`](TASK-EVENT-STREAM-RFC.md) (task/event infra + 5-step migration shape),
[`KEA-MIGRATION-BACKLOG.md`](../backlog/KEA-MIGRATION-BACKLOG.md) §2 (MIGR-02).
**Depends on:** [`ops/KEYCLOAK-IDENTITY-BOOTSTRAP-S3NS.md`](../ops/KEYCLOAK-IDENTITY-BOOTSTRAP-S3NS.md) (MIGR-04 — identity must exist first).

**Migration topic:** this RFC is the **metadata** topic — one of the four migration topics
(**identity → data → metadata → products**). It runs **after** identity (MIGR-04) and **data**
(MIGR-06, the `mc mirror` of document binaries) and **before** products (MIGR-07, re-vectorize).
Vocabulary and order: [`KEA-MIGRATION-BACKLOG.md` → "Migration model"](../backlog/KEA-MIGRATION-BACKLOG.md).

---

## 0. Status & team handoff (WIP — read before branching)

This feature is **work in progress on both ends**, intentionally documented here on the swift
side because **all import/export RFCs live on swift** (kea is being retired). The validation path
is: **first produce an export from kea, then import it with swift.**

**Done (on the current branch, safe to build on):**
- `control_plane_backend/migration/agent_map.py` (+ tests) — the kea→swift agent template
  classification (§7).
- Frontend admin page `/admin/migration` — upload a `.zip`, launch, follow progress via the shared
  task atoms. The launch button POSTs to the not-yet-existing backend endpoint (shows an inline
  error until it lands).

**Not done yet (pick up from fresh branches):**
- **Backend import service** — `POST /control-plane/v1/migration/import`, the `PlatformImportWorkflow`
  Temporal workflow + activities, `MigrationDetail` event, the KF relational import endpoint, OpenFGA
  tuple restore, worker registration (§5, MIGR-05.01–05.05).
- **Stage reconciliation** (this addendum, below) and the **re-vectorize trigger** (MIGR-07).

**Known incompleteness on the kea side:** the kea export itself may not be complete yet (verify the
real bundle against §3 — e.g. an early test bundle had `users: 0`, `teammetadata: 0`,
`realm_exported: false`, `content_keys: []`). Treat the bundle contract in §3 as the target, and
reconcile with the real kea export as it matures. **Export gaps are kea's to fix; the import is
designed to the §3 contract.**

---

## Canonical contract — dumb export, smart import

This is the governing principle for **every** import/export path (kea→kea and kea→swift):

- **Export is dumb.** It dumps the source verbatim — all rows, all tuples, **all status flags** —
  with no reconciliation and no assumptions about the target. The bundle is a truthful snapshot of
  the source. (Today: metadata + OpenFGA tuples + banners; **not** document binaries, **not** vectors.)
- **Import is smart.** Only the importer knows *what it actually restored*, so it reconciles the
  target's metadata to reality. The same dumb bundle can yield different target states under
  different importers (kea-import vs swift-import).

### Stage reconciliation (import-side, mandatory)

Documents carry per-stage processing flags. Swift's model is `ProcessingStage` in
[`document_structures.py:32`](../../../apps/knowledge-flow-backend/knowledge_flow_backend/common/document_structures.py)
— `PREVIEW_READY="preview"`, `VECTORIZED="vector"`, `SQL_INDEXED="sql"` — held on
`DocumentMetadata.processing`, mutated via `set_status(stage, status)` / `mark_stage_done(stage)`
(status set: DONE / IN_PROGRESS / NOT_STARTED / ERROR). This is the same model as kea's
`metadata.processing.stages` / `ProcessingStage`.

A dumb export typically carries `VECTORIZED: DONE`. But **vectors are never transported** — they are
rebuilt on the target. So the importer **must rewrite stage flags to reflect what it actually put in
place**, not what the source claimed; otherwise the metadata lies and the platform audit (correctly)
reports `missing_vectors` while the index is empty.

Rule the swift importer applies after restoring each document's metadata row:
- **`VECTORIZED` and `SQL_INDEXED` → reset to `NOT_STARTED`** (never in the bundle; rebuilt by MIGR-07).
- **`PREVIEW_READY`:** keep `DONE` **only if** the document's `output/` artifacts (markdown, media)
  are present in the target content store; otherwise reset to `NOT_STARTED` and let the target
  regenerate them.

Net state of a migrated document: **visible and previewable/downloadable, but "search pending"**
until re-vectorization completes — and the audit reports the truth.

### Ordering decision (data-mirror vs import)

The fixed migration order is **data (MIGR-06) before metadata (MIGR-05)** — the `mc mirror` of
`input/` **and** `output/` runs before the import. **Decision: the importer trusts content presence**
on that guarantee, so it keeps `PREVIEW_READY: DONE` and only resets the vector/sql stages.
Defensive belt-and-braces: the importer *may* still probe the content store for `output/<uid>/` and
fall back to resetting `PREVIEW_READY` if absent — cheap and removes the ordering dependency. The
runbook ([MIGRATION-CASTLE-TO-S3NS](../ops/MIGRATION-CASTLE-TO-S3NS.html)) must state the ordering
guarantee explicitly.

### Hard dependency — the re-vectorize trigger

Resetting a stage to `NOT_STARTED` is **inert unless something re-processes those documents**. That
"something" is the post-import re-vectorization ([`CORPUS-REVECTORIZE-RFC.md`](CORPUS-REVECTORIZE-RFC.md),
MIGR-07): the migration's final step triggers re-vectorize over the migrated scope, which consumes the
`NOT_STARTED` vector stages and flips them to `DONE`. The stage reset and the re-vectorize trigger are
**two ends of one flow** — neither is complete without the other.

---

## 1. Problem

Kea ships a minimal **export** that bundles durable platform configuration into a timestamped
`.zip` (postgres rows + OpenFGA tuples + manifest). Swift needs the **import** counterpart: a
platform admin uploads the zip and schedules an import task that repopulates an *empty* swift
instance with an equivalent configuration graph. The kea export code is throwaway; the swift
import must be **rock-solid**, observable (Temporal + task/event stream), and surfaced through a
clear progress UI built from the existing task atoms/molecules.

## 2. Scope (confirmed)

**In scope — restore the configuration + authorization graph only:**
agents, prompts/chat-contexts (`resource`), tags, document **metadata**, MCP servers,
team metadata, users, and OpenFGA tuples.

**Conflict policy — fresh target only:** the import refuses to run if the target tables / OpenFGA
store already contain relevant data. No upsert, no overwrite, no merge.

**Explicitly out of scope (handled by sibling topics, not this RFC):**
- **data** — document **binaries** (the bundle's `content_keys` is empty). They are **not**
  re-ingested; they arrive via the **`mc mirror`** of the MinIO buckets, key-for-key, joined back
  to metadata by `document_uid` (MIGR-06). This import only restores their **metadata rows**.
- **products** — **vector embeddings** (OpenSearch) are **rebuilt on the target** by re-vectorize
  (MIGR-07), not transported.
- **identity** — the **Keycloak realm** is bootstrapped first with identical users + groups,
  **IDs preserved** (MIGR-04). This import **validates** referenced identities exist; it does not
  create them. (Team membership is not in the tuples — it derives from group claims.)
- **Conversations / sessions / message history.**

## 3. Bundle contract (observed from `kea-snapshot-*.zip`, format_version 1)

```
manifest.json            # format_version, source_platform, created_at, tables{...},
                         #   tuple_count, realm_exported(bool), content_keys[]
postgres/
  tag.jsonl              # tag_id,name,owner_id,path,description,type,doc,created_at,updated_at
  metadata.jsonl         # document_uid,source_tag,date_added_to_kb,tag_ids[],doc,created_at,updated_at
  resource.jsonl         # resource_id,resource_name,resource_type,author,doc,created_at,updated_at
  mcp-server.jsonl       # server_id,payload_json,created_at,updated_at
  agent.jsonl            # id,name,payload_json{...,definition_ref,class_path,...},created_at,updated_at
  teammetadata.jsonl     # (may be empty)
  users.jsonl            # (may be empty)
openfga/
  tuples.json            # [{user,relation,object}]  — store "kea"
```
One JSON object per line; last line may lack a trailing newline (manifest counts are authoritative).

## 4. Target mapping & transforms

| Bundle table | Swift target (file) | Transform |
|---|---|---|
| `tag` | `tag` — `knowledge-flow-backend/.../tags/tag_models.py` | 1:1 |
| `resource` | `resource` — `.../resources/resource_models.py` | drop/fold `created_at`/`updated_at` (no such cols in swift); covers prompts/chat-contexts |
| `metadata` | `metadata` — `.../metadata/metadata_models.py` | same timestamp note |
| `agent` | **`agent_instance`** — `control-plane-backend/.../models/agent_instance_models.py` | **decompose** `payload_json` → `template_id`, `source_runtime_id`, `source_agent_id`, `tuning_json`, `prompt_refs_json`; inject `team_id`, `created_by`; map kea `class_path`/`definition_ref` via an **agent catalog mapping** (see §7 risk) |
| `mcp-server` | none (MCP refs live inline in agent tuning) | fold into agent restore / dedupe; no standalone table |
| `teammetadata` | `teammetadata` — `fred-core/.../team_metatada_models.py` | map; default swift-only cols (`is_private`, storage sizes, banner) |
| `users` | `users` — `fred-core/.../users/user_models.py` | map `id`; default GCU/storage |
| `openfga/tuples.json` | swift `fred` OpenFGA store | write tuples; **validate** user/team/object existence; conform to `schema.fga`; reconcile `team:personal*` with `personal_team_id(uid)` |

Both backends share one Postgres DB (`fred`); the import (in control-plane) writes knowledge-flow
tables directly or via a thin knowledge-flow restore call — to be decided in §7.

## 5. Architecture — mirror the ingestion pipeline (Temporal + fred-core task/event)

The import is implemented as a **Temporal workflow in control-plane** that drives progress through
the **fred-core task/event API**, so the existing frontend task atoms render it with zero new event
plumbing. It deliberately mirrors the knowledge-flow **ingestion** pipeline so the team reuses one
pattern. Reference implementation to copy:

| Ingestion (reference) | Import (this RFC) |
|---|---|
| `features/scheduler/workflow.py` `ProcessPullFile.run` (emit → stages → emit) | `migration/workflow.py` `PlatformImportWorkflow.run` |
| `features/scheduler/activities.py` `output_process` etc. | `migration/activities.py` (`validate_bundle`, `preflight`, `restore_relational`, `restore_agents`, `restore_openfga`, `verify`) |
| `activities.py:122` `emit_ingestion_task_event` → `task_service.record(IngestionTaskEvent(IngestionDetail))` | `emit_migration_task_event` → `task_service.record(MigrationTaskEvent(MigrationDetail))` |
| `ingestion_controller.py:511` `task_service.start(...)` then `client.start_workflow(..., task_queue="ingestion")` | `migration/api.py` `task_service.start(kind="migration")` then `client.start_workflow("PlatformImportWorkflow", task_queue="control-plane-lifecycle")` |
| `scheduler/worker.py` registers workflows + activities | register `PlatformImportWorkflow` + activities in control-plane `scheduler/temporal/worker.py` |

**1. Upload + start** (`migration/api.py`, admin-only via `require_admin`):
`POST /control-plane/v1/migration/import` (multipart zip) → stash zip in object storage
(`migration-imports/{import_id}.zip`) → `task = task_service.start(StartTaskRequest(kind="migration",
target=TaskTarget(type="platform", id=import_id)), created_by=user.uid)` → `client.start_workflow(
"PlatformImportWorkflow", {task_id, zip_key}, id="import-{import_id}", task_queue="control-plane-lifecycle")`
→ return `202 {task_id, import_id}`.

**2. Workflow** (`migration/workflow.py`) — ordered, retryable activities, each bracketed by an emit,
exactly like `ProcessPullFile`:
```
validate_bundle (manifest format_version, counts)   emit step=validate      progress .0
preflight (FRESH-TARGET guard + identity exists)    emit step=preflight     progress .1
restore_relational (tag/metadata/resource/team/users) emit step=relational  progress .2
restore_agents (agent → agent_instance via map)     emit step=agents        progress .5
restore_openfga (tuples; validate; personal-team)   emit step=openfga       progress .75
verify (counts vs manifest, dangling refs)          emit step=verify        progress .9
                                                    emit state=succeeded     progress 1.0
on exception: emit state=failed, error=...
```

**3. Event model** — add `MigrationDetail {step_id, processed, total, failed}` to
`fred-core/tasks/models.py` (sibling of `IngestionDetail`). The frontend already declares the matching
`MigrationTaskEvent` type (`features/tasks/taskTypes.ts`) and a `migration` task kind — so the UI side
is mostly wiring, not new types.

**4. Cross-backend (resolves §4's open question — recommended).** `restore_relational` writes the
knowledge-flow-owned tables (`tag`, `metadata`, `resource`) by calling a **thin synchronous KF admin
endpoint** (`POST /knowledge-flow/v1/admin/import/relational`) over httpx (pattern at
`product/service.py:1021`), keeping each backend the owner of its tables. Control-plane writes its own
domain directly: `agent_instance` (via `enroll_agent_instance`), `users`/`teammetadata` (fred-core),
and the OpenFGA tuples. `mcp-server` is **skipped** (re-seeded by deployment).

**5. UI** — `/admin/migration` page: drop zip → POST → `taskRegistered({kind:'migration'})` → live
progress via the task SSE → 6 step cards (`TaskCard`/`BatchStepCard`) → pass/fail. Admin-only. (See
frontend plan; most types/atoms already exist.) **Note:** `useTaskSseManager` currently hardcodes the
knowledge-flow task-events URL; it must resolve the events base per task kind (control-plane for
`migration`).

**6. SSE source.** The import task lives in control-plane, so events stream from control-plane
`tasks/api.py:/tasks/{id}/events`. The KF relational sub-call is synchronous (small data) and reports
into the same control-plane task via the activity's emit — one task_id, one progress stream.

**7. Idempotency / robustness** — `preflight` fresh-target guard refuses a populated target; Temporal
gives retries + restart-safety per activity. No merge into populated tables (per §2 scope).

## 6. Products phase — post-import re-vectorization (MIGR-07)

A config-only import restores agents/prompts/metadata + the document **metadata** rows, and the
document **binaries** arrive via the data mirror — but **embeddings are not migrated** (products are
rebuilt). The final migration phase rebuilds them. This is designed in
[`CORPUS-REVECTORIZE-RFC.md`](CORPUS-REVECTORIZE-RFC.md): a knowledge-flow Temporal workflow that
re-runs the existing `output_process` activity over the migrated documents, streaming progress on the
same task/event infra. The migration UI surfaces it as the last step ("Rebuild embeddings"),
reusing the same atoms.

Other out-of-scope follow-ups (not built here): extending the kea export to bundle binaries;
conversation/session restore.

## 7. Agent mapping — consolidated spec (resolves the crux)

Scope is **user-created agent instances only**; kea built-in samples are not migrated. A kea agent's
template identity is its v2 `definition_ref` (e.g. `v2.react.basic`) or, for legacy agents, its v1
top-level `class_path`. The transform maps that identity to a swift template id in
`{source_runtime_id}:{source_agent_id}` form, validated at import against the live fred-agents
`/agents/templates` catalog. Implemented in `migration/agent_map.py` (+ `tests/test_agent_map.py`).

**Three-state classification** (the mapping table is the single control point):

| Outcome | Meaning | Action |
|---|---|---|
| **mapped** | template is in `KEA_TO_SWIFT_TEMPLATE` | create the `agent_instance` |
| **ignored** | a known kea sample/demo (`v2.sample.*`, `v2.deep.*`, dva validators…) | skip — not user data |
| **gap** | anything else (incl. unresolvable template) | **build the equivalent in fred-agents**, add the mapping, re-run |

Mappings (real swift ids):

| kea template | swift template id |
|---|---|
| `v2.react.basic` | `fred-agents:fred.github.assistant` |
| `v2.production.sql_analyst` | `fred-agents:fred.github.sql_expert` |
| `…prometheus_expert.Spot` | `fred-agents:fred.github.sentinel` |
| `…rag_expert.Rico` | `fred-agents:fred.github.rag_expert` |
| `…tabular_expert.Tessa` | `fred-agents:fred.github.sql_expert` |

**Gap policy is "fill, not skip":** `preflight` classifies every agent and emits the gap list; a real
cutover requires **zero gaps**. This converts the former correctness risk into an enforced, visible
checklist. (`preflight` may run report-only during iteration; it blocks at cutover.)

## 8. Remaining open items
- **Stage reconciliation API** — `restore_relational` must call `set_status(VECTORIZED, NOT_STARTED)`
  (and `SQL_INDEXED`) per migrated document, and conditionally reset `PREVIEW_READY` (see the
  canonical-contract section). Confirm the exact write path through `DocumentMetadata.processing`.
- **Re-vectorize trigger** — MIGR-07 must actually consume the reset stages (the inert-flag risk).
  Specify the trigger (migration final step → `/corpus/revectorize` over the migrated scope).
- **Data-vs-import ordering** — document the "data mirrored before import" guarantee in the runbook,
  or have the importer probe the content store defensively (decision recorded above: trust + optional probe).
- **Personal-team tuples**: bundle references `team:personal*`; swift derives personal teams via
  `personal_team_id(uid)` — restore must reconcile, not blindly insert.
- `metadata`/`resource` timestamp columns absent in swift — confirm fold-into-`doc` vs add-columns.
- **Kea export completeness** — reconcile §3 contract with the real kea export as it matures (export
  gaps are kea's to fix).

## 9. Decision requested
Approve scope (§2) + architecture (§5) + agent mapping (§7) + the dumb-export/smart-import contract
(stage reconciliation) so this can become MIGR-05 implementation work (control-plane import service +
Temporal workflow + admin UI), tracked in `KEA-MIGRATION-BACKLOG.md`.
