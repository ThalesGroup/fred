# RFC — Platform Import service (kea→swift configuration restore)

**ID:** MIGR-05 · **Status:** partially implemented — agents + tags + document metadata land atomically; export / reset / stats shipped; prompts, OpenFGA tuples, stage-reconciliation deferred
**Owner:** Dimitri · **Surface:** control-plane-backend + frontend
**Extends:** [`TASK-EVENT-STREAM-RFC.md`](TASK-EVENT-STREAM-RFC.md) (task/event infra),
[`KEA-MIGRATION-BACKLOG.md`](../backlog/KEA-MIGRATION-BACKLOG.md) §0bis (MIGR-05).
**Depends on:** [`ops/KEYCLOAK-IDENTITY-BOOTSTRAP-S3NS.md`](../ops/KEYCLOAK-IDENTITY-BOOTSTRAP-S3NS.md) (MIGR-04 — identity must exist first).
**Operational model:** [`ops/KEA_SWIFT_CUTOVER.md`](../ops/KEA_SWIFT_CUTOVER.md).

**Migration topic:** this RFC is the **metadata** topic — one of the four migration topics
(**identity → data → metadata → products**). It runs **after** identity (MIGR-04) and **data**
(MIGR-06, the `mc mirror` of document binaries) and **before** products (MIGR-07, re-vectorize).
Vocabulary and order: [`KEA-MIGRATION-BACKLOG.md` → "Migration model"](../backlog/KEA-MIGRATION-BACKLOG.md).

---

## 0. Status & team handoff (read before branching)

This feature is documented here on the swift side because **all import/export RFCs live on swift**
(kea is being retired). The validation path is: **first produce an export from kea, then import it
with swift.**

### Implementation note — architecture deviation from §5 (2026-06-27)

The shipped implementation **does not use Temporal** (§5 below remains the future design if payloads
grow). For a config-sized payload (one shared `fred` Postgres DB, sub-megabyte zip), a single
**atomic SQLAlchemy transaction inside a FastAPI `BackgroundTask`** is simpler and gives a stronger
guarantee than per-activity retries: **all writes (agents + tags + metadata) commit together or roll
back together — no partial state**. Progress still streams through the fred-core task/event API
(`MigrationTaskEvent`), so the frontend task atoms render it unchanged. If/when binaries or
large multi-store restores enter scope, revisit the Temporal design in §5.

- **Module:** `control_plane_backend/import_export/` (not `migration/`).
- **Endpoints** (all `require_admin`, prefix `/control-plane/v1`):
  - `POST /import-export/import` — multipart zip → async task; atomic import.
  - `GET  /import-export/export` — download a **swift-native** snapshot (`source_platform=swift`),
    re-importable through the same importer (a native branch skips the kea `agent_map` translation).
  - `POST /import-export/reset` — atomic wipe of agents + tags + metadata (enables
    export → reset → import test cycles; Keycloak / OpenFGA / object store untouched).
  - `GET  /import-export/stats` — relational platform overview (teams, members by role, agents,
    prompts; personal spaces aggregated). Powers the **Platform data** admin page.

**Done (on the current branch, reviewed + live-tested):**
- `import_export/agent_map.py` (+ `tests/test_agent_map.py`) — kea→swift agent classification (§7).
- `import_export/bundle.py` — bundle reader + manifest parse (kea + swift formats).
- `import_export/importer.py` — atomic import of **agents** (mapped; IGNORED skipped; GAP warned),
  **tags**, **document metadata**, in one transaction; idempotent by primary key (safe re-run).
- `import_export/exporter.py` — swift-native snapshot writer.
- `import_export/stats.py` — platform summary aggregation.
- `MigrationTaskEvent` populated with `step` + `progress`; control-plane added to frontend task
  rehydration + SSE sources, so migration tasks survive reload.
- Admin page (renamed **Platform data**) — import / export / reset + the live stats dashboard.
- `import_export/importer.py::_run_users_phase` (+ `bundle.py::demo_users`,
  `users/service.py::find_user_sub_by_username`) — declarative team/platform role provisioning from
  the new `users.json` bundle entry (§10, AUTHZ-07 Part 8 §40.2), **team-role reconciliation fixed
  2026-07-14 (AUTHZ-07 Step 2 — see §10's "Team-scoped roles" subsection)** after the first pass's live
  validation run surfaced a design gap: non-admin team-scoped grants were unconditionally refused by the
  `team_admin`-gated ordinary API and downgraded to warnings while the import still reported
  `succeeded`. **Live-validated 2026-07-14**: re-imported the same demo bundle onto the
  already-partially-provisioned live stack, then re-ran root `make validation-report` —
  **225 passed, 0 failed, 0 errors, 2 skipped (expected)**, confirming the fix closes the gap end to end,
  not just offline.
- `import_export/api.py` (§11, AUTHZ-07 Step 3) — the import task now carries a canonical, durable
  `TaskTarget` and its terminal `succeeded` event carries the full structured `MigrationReport` (via
  `fred_core.tasks.models.MigrationDetail.result`), so a partial reconciliation (warnings) is never
  indistinguishable from full success after a reload. See §11.

**Deferred (not done — tracked in backlog §0bis):**
- **Prompts/resources** — agents import with default tuning only; kea agent prompt → swift agent
  instance prompt is **not** transferred yet (MIGR-05.11, the explicit next gap).
- **OpenFGA tuple restore** (MIGR-05.04) — handled out-of-band by ops bulk-copy (cutover Option A);
  `reset` deliberately leaves tuples intact so team ownership survives a re-test.
- **Stage reconciliation** (MIGR-05.07) + **re-vectorize trigger** (MIGR-07).
- ~~**users / MCP** restore — re-seeded by deployment / identity bootstrap (MIGR-04)~~ **partially
  superseded (2026-07-14, §10):** this line meant the kea `postgres/users.jsonl` table (Keycloak
  identity rows) — still correctly out of scope, identity stays MIGR-04's job. A *different*,
  top-level `users.json` bundle entry (not a `postgres/` table) now exists for a separate concern:
  declarative Fred-side authorization provisioning (team roles, platform roles) for identities that
  already exist. See §10. **MCP** restore is still fully deferred (unchanged).
- ~~**teammetadata** restore — re-seeded by deployment / identity bootstrap~~ **superseded
  (2026-07-10):** this assumed team metadata was Keycloak-identity-derived, which was true only
  while teams were Keycloak groups. AUTHZ-05 review item 9 decoupled teams from Keycloak entirely
  — `import_export/importer.py::_import_team_metadata` already restores `teammetadata` rows
  (including the now-required `name` column, with an id-fallback for older bundles) as part of
  the same import transaction as agents/tags/document metadata, not a separate identity-bootstrap
  step. Update this line's status if that changed since.
- **Fresh-target preflight guard / verify step** — superseded by idempotent-by-PK import + `reset`.

**Known incompleteness on the kea side:** verify the real bundle against §3 (an early test bundle had
`users: 0`, `teammetadata: 0`, `realm_exported: false`, `content_keys: []`). Treat §3 as the target;
**export gaps are kea's to fix; the import is designed to the §3 contract.**

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
- **identity** — the **Keycloak realm** is bootstrapped first with identical users,
  **IDs preserved** (MIGR-04). This import **validates** referenced identities exist; it does not
  create them. Team membership is **not** derived from Keycloak groups (AUTHZ-05 review item 9,
  `FRED-AUTHORIZATION-TARGET-MODEL-RFC.md` Part 6) — a team is a `team_metadata` row (which this
  import already restores, including the now-required `name` column) plus explicit OpenFGA
  membership tuples (`team_admin`/`team_editor`/`team_analyst`/`team_member`), which **are** part
  of the imported tuple set like any other relation.
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
| `teammetadata` | `teammetadata` — `fred-core/.../team_metatada_models.py` | map; default swift-only cols (`is_private`, storage sizes, banner); `name` is now required (AUTHZ-05 review item 9) — fall back to the id if the source bundle predates it |
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
- **Agent prompt transfer (MIGR-05.11) — the next gap.** Imported agents currently land with default
  tuning only (`role`/`description` = display name) and **no prompt content**. Kea agents carry their
  prompt(s) in `agent.payload_json` (system/tuning prompt text); swift agent instances reference
  prompts via `prompt_refs_json` → team-scoped `prompt` rows (`PromptRow`, unique on `(team_id, name)`).
  The importer must, per mapped agent: create/locate a `prompt` row owned by the agent's `team_id`
  holding the kea prompt text, and wire the new `agent_instance.prompt_refs_json` to it. Until then the
  **Prompts** column in the Platform-data stats stays at 0 for imported agents.
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

## 10. Declarative team/platform role provisioning — `users.json` (2026-07-14)

This is the confirmation/implementation `FRED-AUTHORIZATION-TARGET-MODEL-RFC.md` Part 8 §40.2
("Platform provisioning") asked for: *"the likely right move is to harden and generalize
[`PLATFORM-IMPORT-RFC.md`]'s input contract... to be confirmed with whoever owns that RFC before any
implementation."* Part (2) of `AUTHZ-07`'s original scope (declarative platform provisioning for
teams/roles/users, tracked open in `AUTHZ-MIGRATION-BACKLOG.md`'s AUTHZ-07 rows) is closed by this
section.

**Bundle addition.** A new top-level `users.json` entry (sibling of `manifest.json`/`openfga/`, **not**
under `postgres/` — these are not Postgres rows, they are a typed (`import_export/schemas.py::BundleUserEntry`)
description of the Keycloak identity and the Fred-side authorization state a user should end up with):

```json
[
  {"username": "alice", "email": "alice@app.com", "first_name": "Alice", "last_name": "Watson",
   "password": "Azerty123_", "teams": [], "team_roles": {"team_admin": ["fredlab"]}, "platform_roles": ["admin"]},
  {"username": "bob", "teams": ["fredlab"], "team_roles": {"team_editor": ["fredlab"]}, "platform_roles": []}
]
```

`BundleUserEntry`'s full shape: `username: str` (required); `email`/`first_name`/`last_name`/`password:
str | None = None` (identity-phase fields, all optional — see the 2026-07-14 addendum below);
`teams: list[str] = []`, `team_roles: dict[str, list[str]] = {}`, `platform_roles: list[str] = []`
(role-phase fields, unchanged). One format, because it's one file: each phase reads what it needs from
the same entry and ignores the rest — `bob` above has no identity fields and is treated exactly as
before (assumed to already exist). `KBundle.demo_users()` reads and validates it
(`BundleUserEntry.model_validate` per entry), mirroring `openfga_tuples()`'s try/except-`KeyError`-
return-`[]` pattern around the zip read itself (`bundle.py`). `teams` names every team a user should be
provisioned into; `team_roles` maps a relation (`team_admin`/`team_editor`/`team_analyst`/`team_member`)
to the team names it should be granted on; `platform_roles` (`"admin"` → `platform_admin`, `"observer"`
→ `platform_observer`) grants org-level roles.

**Design principle — the role phase never creates an identity; the identity phase creates one only when
explicitly asked.** Consistent with AUTHZ-05's Keycloak-is-identity-only model, the role phase resolves
`username` → Keycloak `sub` via **read-only** `users/service.py::find_user_sub_by_username` (the same
read-only admin client `list_users`/`get_users_by_ids` already use — never the write-gated M2M path
`create_user` requires). A username still unresolved after the identity phase (below) is **skipped and
reported** (`report.users_skipped`, `report.warnings`), never created by this phase and never failing
the rest of the import.

**The new capability — granting a platform role to a third party.** Before this change, the only path
to `platform_admin`/`platform_observer` was `bootstrap/service.py::bootstrap_platform_admin`'s
self-promotion-only endpoint (RFC Part 8 §42.2: "the grant always targets the calling JWT's own
`sub`"). `users.json`'s `platform_roles` is the first path that can name a **third party**. It is
deliberately **not** a new public service function or endpoint: `importer.py::_grant_platform_role` is
a small private helper, reachable only through `POST /import-export/import`, which already requires
`OrganizationPermission.CAN_MANAGE_PLATFORM` as the first line of the route handler (`api.py`,
unchanged by this work — the new phase rides the same existing gate, no second check added). This is
not a privilege-escalation path: granting `platform_admin` to someone else already requires being a
`platform_admin` yourself, exactly the same shape as any other admin capability in this system. The
call mirrors `bootstrap_platform_admin`'s own direct `rebac.add_relation(...)` — `add_relation` is
idempotent (`on_duplicate_writes=IGNORE`), so re-running the same bundle never errors on an
already-granted role.

**Team-scoped roles — bounded by the existing permission model, not bypassed. Revised 2026-07-14
(AUTHZ-07 Step 2 — reconciliation fix).** `schema.fga`'s `type team` comment is still explicit and was
tested in review (§24.2/§24.7): team-scoped relations (`team_admin`/`team_editor`/`team_analyst`/
`team_member`) are **never** derived from a platform role — "a `platform_admin from organization`
exception was tried for team bootstrap and reverted the same day." This importer does not reopen that
door; `schema.fga` is untouched by this fix. Two consequences, both implemented and covered by
`tests/test_import_export_users.py`:
- A **brand-new** team's initial `team_admin`(s) is seeded at creation time
  (`teams.service.create_team`'s own one-shot, `CAN_CREATE_TEAM`-gated bootstrap capability —
  `CreateTeamRequest.initial_team_admin_ids`), by collecting every `team_admin` the bundle declares for
  that team before creating it. `CAN_CREATE_TEAM` is org-wide (`platform_admin`), so this needs no
  team-scoped permission from the importing caller.
- **Every other team-scoped grant** — `team_editor`/`team_analyst`/`team_member` on any team, or any
  role at all on a team that already existed before this import — is now written through
  `importer.py::_grant_team_role_via_import`, a **private, import-only reconciliation primitive** that
  calls `RebacEngine.add_relation` directly, mirroring `_grant_platform_role`'s own direct-write shape.
  This is the fix: the first implementation (2026-07-14, superseded by this revision the same day) routed
  every such grant through the existing `teams.service.grant_team_member_role`, which requires the
  importing `platform_admin` to already hold `team_admin` on that specific team — a condition the
  importer deliberately never satisfies (RFC Part 8 §24.2/§24.7, "zero implicit access"). That made
  every non-admin team-scoped grant in a real bundle unconditionally refused and downgraded to a
  warning while the import still reported `succeeded` — confirmed live: importing the 15-identity demo
  bundle produced exactly 10 skipped grants (bob/phil/zoe/liam/elena/derek/priya's non-`team_admin`
  roles) out of 14 declared, which then cascaded into 227 setup errors in `validation/report.md` (every
  scenario's fixture setup depends on the full role matrix being present). `_grant_team_role_via_import`
  closes this without weakening the *ordinary* permission model: `grant_team_member_role`/
  `add_team_member`/etc. are completely unchanged and still require `team_admin`, proven by a dedicated
  regression test (`test_grant_team_member_role_still_requires_team_admin_for_the_importer`) that calls
  the ordinary API with the same importer identity and asserts it still raises `AuthorizationError`. The
  new primitive is reachable only from `POST /import-export/import` (already `CAN_MANAGE_PLATFORM`-gated,
  no second check added) and is never exposed as a second public team-membership service — same shape
  and same safety argument as `_grant_platform_role`.

**`teams`/`team_roles` semantics (`importer.py::_effective_team_relations`, formalized 2026-07-14).**
Per bundle entry, per team: if the team name is a value anywhere in that entry's `team_roles`, the
requested state is **exactly** the named relation(s) on that team — multiple roles on the same team are
**cumulative** (e.g. priya: `team_admin` + `team_editor` + `team_analyst` on `fredlab`, all three
persisted as direct tuples). If the team name appears in `entry.teams` but is **never** a `team_roles`
value for that same entry, the requested state is a single direct `team_member` tuple — the only
fallback. A team with an explicit role never *also* gets the direct `team_member` tuple: `schema.fga`
already derives `team_member` as a union over `team_admin`/`team_editor`/`team_analyst`, so writing it
directly on top would be redundant, not additive.

**Fail-closed, not warn-and-succeed (AUTHZ-07 Step 2).** A declared-valid bundle must never produce a
silently incomplete `succeeded` import. `importer.py::BundleProvisioningError` is raised — aborting the
whole users phase, which `import_export/api.py`'s background-task wrapper turns into
`task_service.fail_task` — for every one of: an unknown `team_roles` key or `platform_roles` value
(validated upfront, before any write); a username still unresolved after the identity phase; a team
referenced by the bundle (via `teams` or `team_roles`) that does not already exist and has no
`team_admin` declared for it anywhere in the bundle (so `create_team` cannot seed it). None of these are
downgraded to a warning anymore. **Idempotence is preserved**: `add_relation`'s
`on_duplicate_writes=IGNORE` means re-running an already-fully-reconciled bundle re-writes the same
tuples with no error and no duplicate — `report.team_roles_granted` counts every declared grant on every
run, whether or not the underlying write was a no-op.

**Report fields** (`importer.py::MigrationReport`, folded into the existing task-event summary string,
same as every other phase — no new HTTP response field, since the report was never returned over HTTP
to begin with, only surfaced via the `MigrationTaskEvent.step` string and server logs):
`identities_created` (see the addendum below), `users_processed`, `users_skipped` (list of unresolved
usernames — now vestigial, always `[]` on a report that made it back to the caller, since an unresolved
username raises instead; kept on the dataclass for API stability and for AUTHZ-07 Step 3), `teams_provisioned`
(distinct name from the pre-existing `teams_imported`/`teams_skipped`, which count `team_metadata`
Postgres rows, not teams created via this phase), `team_roles_granted`, `team_roles_skipped` (same
vestigial note as `users_skipped` — always `0` now), `platform_roles_granted`.

### 10.1 Identity phase — bundle-driven Keycloak user creation (2026-07-14)

Closes the remaining part of the `fred`/`fred-deployment-factory` boundary split: `fred`
(`control_plane_backend/import_export/`) is now the sole, complete owner of platform provisioning — both
the Keycloak identities and the Fred authorization state — in the one typed, versioned, git-committed
`users.json` format described above. `fred-deployment-factory` carries no user/team data of its own.

**What runs, and in what order** (`importer.py::_run_users_phase`): phase 1
(`_provision_bundle_identities`) runs first, then phase 2 is the role-provisioning logic described
above, unchanged. For each bundle entry, phase 1 creates a Keycloak user via the existing
`users/service.py::create_user` (already Keycloak-Admin-M2M-gated — no new Keycloak capability, just a
new caller) **only if both** conditions hold: (a) `find_user_sub_by_username` finds no existing match,
and (b) the entry carries a `password`. An entry with no `password` is assumed to already exist and is
never force-created — it falls through to phase 2's read-only resolution exactly as before, and is
skipped/reported there if it still doesn't resolve. Phase 1 never overwrites an already-existing
identity. Running phase 1 before phase 2 means a bundle that creates *and* grants roles to the same
identity, in the same entry, works in a single import call — not two separate uploads.

**Precondition.** Any bundle that creates identities requires Keycloak Admin M2M credentials to be
configured (the same precondition `create_user`/`delete_user` already have via
`_get_keycloak_admin_for_user_operations`). If they are not configured, `create_user` raises
`KeycloakM2MUserOperationDisabledError`, which this phase lets propagate rather than swallowing — the
import fails loudly with a clear cause instead of silently skipping every identity-creation entry. A
bundle whose entries carry no `password` (already-existing identities only) has no such precondition —
phase 1 is then a no-op for every entry, same as before this addendum.

**Report field.** `report.identities_created` counts Keycloak users created by phase 1, folded into the
same task-event summary string as every other phase field.

**The fixture.** `apps/control-plane-backend/tests/fixtures/import_export/demo_provisioning/`
(`manifest.json` + `users.json`) is the single, checked-in, git-committed source of truth for every demo
identity *and* every team/platform role — the data that used to live in
`fred-deployment-factory/config/configuration.yaml`'s `users:` list now lives here exclusively, typed
through `BundleUserEntry`. `make build-demo-bundle` (`apps/control-plane-backend/Makefile`) zips the two
fixture files into `target/demo-provisioning-bundle.zip` for upload via Admin → Migration. No top-level
`teams:` list is needed in the fixture — every team name is derivable by unioning `entry.teams` and
`entry.team_roles.values()` across all entries.

## 11. Observable, durable, truthful import outcome (AUTHZ-07 Step 3, 2026-07-14)

Step 2 (§10, above) made reconciliation *complete* — a declared-valid bundle either fully provisions or
fails closed. It did not make the result *observable*: `import_export/api.py` discarded the
`MigrationReport` `run_import()` returned and emitted an empty terminal `succeeded` event with no target
beyond the raw `import_id` UUID. A live import (Step 1's evidence, §"Step 1" above) showed the operator
only a bare UUID and the word "Terminé" — a partial reconciliation (silently-skipped grants, before the
Step 2 fix) was indistinguishable from full success once the task list reloaded.

**Truth rule.** A `succeeded` platform-import task is not always a *clean* success — it may have produced
warnings during a phase that does not itself fail closed (e.g. an agent classified `GAP`, §7). The
terminal event and `GET /tasks` must let an admin tell the two apart without guessing. **No new
`TaskState` is introduced** (`succeeded` stays `succeeded`, matching `TASK-EVENT-STREAM-RFC.md`'s state
machine) — the tell is a non-empty `result.warnings` list in the structured detail below, which the UI
renders as an explicit "with warnings" flag distinct from a silent success.

**Canonical target.** `import_export/api.py::_import_target` builds the task's `TaskTarget` once, at
launch, before the background import runs: `type="platform_import"`, `id=import_id`, `label=` the
operator-supplied label (trimmed) if non-empty, else the uploaded file's name, else a safe fallback
(`"Platform import"`). This is passed to `task_service.start(..., target=...)`, so it is durable from the
first `GET /tasks` — including if the import fails before any progress event is ever emitted.
`ImportLaunchResponse` also returns this exact `target` (2026-07-14 close-out amendment,
`CONTROL-PLANE-PRODUCT-CONTRACT.md` §16): the frontend's optimistic registration
(`launchPlatformImport.ts` → `MigrationPage.tsx::handleLaunch`) registers the backend's own returned
value directly, rather than reconstructing the same precedence rules a second time — one canonical
target, not two independently-built ones.

**Structured terminal result.** `fred_core.tasks.models.MigrationResult` (a new Pydantic model, sibling of
`MigrationDetail`) is a typed public projection of the internal `MigrationReport`
(`import_export/importer.py`), converted field-for-field by `importer.py::to_migration_result` — the
report's own field computation is not duplicated, only mapped. `MigrationDetail` gained an optional
`result: MigrationResult | None` field (`None` on every intermediate progress event, exactly as before;
populated only on the terminal `succeeded` event). Carries: `import_id`, `source_platform`,
`identities_created`, `users_processed`, `users_skipped`, `teams_imported`/`teams_skipped`,
`teams_provisioned`, `team_roles_granted`/`team_roles_skipped`, `platform_roles_granted`,
`agents_imported`/`agents_skipped`/`agents_gap`, `tags_imported`/`tags_skipped`,
`docs_imported`/`docs_skipped`, `warnings`. Same content-boundary rule as every other task detail
(`TASK-EVENT-STREAM-RFC.md` §3.3): operational counters and warning strings only, never bundle content.

**Durable across reload.** `TaskSummary` (the `GET /tasks` response shape) gained an optional `detail`
field, typed per `kind` exactly like `TaskEvent.detail` (a plain, non-discriminated union of the existing
per-kind Detail models — the frontend narrows on the sibling `kind` field, the same pattern already used
for `TaskEvent`). `TaskStore.list_tasks` projects the last-persisted `TaskRunRow.detail` (already written
by the pre-existing `record_event` "keep the last non-null detail" rule) into the correctly-typed model
for the row's `kind`. Backward compatible: a task with no persisted detail (every kind before this change,
and `log`, which has no summary detail model) reads back `detail: null`.

**Honest failure, unchanged path.** An exception during `run_import()` still drives the task `failed` via
the pre-existing `task_service.fail_task`, unchanged by this step — it already reads the canonical target
from `TaskRunRow.target` (set at creation, per above), so the failure event carries the same target and a
usable `error` message. Never `succeeded` on an exception.

**No parallel model.** This is presentation of the existing canonical pipeline, not a new one:
`MigrationReport` → (`to_migration_result`) → `MigrationTaskEvent.detail.result` → `TaskStore`
("keep the last detail") → `TaskSummary.detail` → the shared `TaskActivity` component. No new table, no
new endpoint, no new Redux store, no import-specific activity page — `GET /tasks` and the existing task
system remain the single source of truth (`TASK-EVENT-STREAM-RFC.md` §3.4).
