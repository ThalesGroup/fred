# RFC — Corpus re-vectorization (products rebuild, post-migration embeddings)

**ID:** MIGR-07 · **Status:** confirmed 2026-07-25 — implementation starts, tracked as
[#2111](https://github.com/ThalesGroup/fred/issues/2111).
**Owner:** Dimitri · **Surface:** knowledge-flow-backend (+ migration UI trigger)
**Extends:** the existing ingestion pipeline (`features/scheduler/`) and the stubbed
`/corpus/revectorize` endpoint. **Sibling of:** [`PLATFORM-IMPORT-RFC.md`](PLATFORM-IMPORT-RFC.md) (the
**products** topic that runs after **metadata** import).
**Migration topic:** **products** — rebuilt on the target, never transported.
**Operational model:** [`ops/KEA_SWIFT_CUTOVER.md`](../ops/KEA_SWIFT_CUTOVER.md).

---

## 1. Problem

After a migration, documents exist as **metadata rows** (restored by the import) and **binaries** in
object storage (restored by the `mc mirror` data step: `<document_uid>/input/…` and `…/output/…`), but
the OpenSearch **vector index has no embeddings**. Search/RAG is dark until embeddings are rebuilt.
We need a robust, observable bulk re-vectorization that streams progress through the fred-core
task/event API like every other long job, and that doubles as a general corpus-maintenance capability.

## 2. What already exists (redesign, don't rebuild)

| Building block | Location | Reuse |
|---|---|---|
| `/corpus/revectorize` endpoint + `RevectorizeCorpusRequestV1` (scope + mode/force) | `features/corpus_manager/corpus_manager_controller.py:80` | **wire it** — currently a mock task |
| `output_process` activity (restore from storage → chunk → embed → index) | `features/scheduler/activities.py:32` | **the core** — re-vectorizes one document from stored content |
| `get_local_copy(document_uid)` (restores input/ + output/ from object storage) | `features/ingestion/ingestion_service.py:166` | lets re-vectorize reuse the mirrored `output.md` (no re-extraction) |
| `delete_vectors_for_document` / `get_document_chunk_count` / `list_document_uids` | `core/stores/vector/opensearch_vector_store.py:861-909` | skip/overwrite decisions |
| `emit_ingestion_task_event` + `IngestionDetail{processed,total,failed,vectorized,…}` | `features/scheduler/activities.py:122` | **reuse verbatim** for progress |

The heavy lifting is done. What is missing is the **bulk orchestration workflow** and wiring the stub
endpoint to it.

## 3. Design — a thin Temporal workflow over existing activities

Mirror the ingestion parent/child pattern (`ProcessPull` → `ProcessPullFile`):

```
POST /knowledge-flow/v1/corpus/revectorize  (admin/owner-only)
  → task = task_service.start(kind="revectorize", target=…)
  → client.start_workflow("RevectorizeCorpusWorkflow", {scope, options, task_id}, task_queue="ingestion")
  → 202 { task_id }

RevectorizeCorpusWorkflow.run(scope, options, task_id):
  uids = await execute_activity(list_documents_in_scope, scope)     # NEW thin activity: metadata query
  emit(running, detail=IngestionDetail(total=len(uids)))
  for batch in chunks(uids, max_parallelism):                       # same batching as ProcessPull
    await gather(start_child_workflow(RevectorizeDocument, uid) for uid in batch)
  emit(succeeded, detail=IngestionDetail(processed, total, failed, vectorized))

RevectorizeDocument.run(uid, options):
  count = await execute_activity(get_chunk_count, uid)
  if options.mode == incremental and not options.force and count > 0:
      emit(step="skip", …); return                                 # already vectorized
  if options.force or count > 0:
      await execute_activity(delete_vectors, uid)
  await execute_activity(output_process, uid, metadata)            # REUSE — restore from storage + vectorize
  emit(step="vectorized", …)
```

**New code is small:** `RevectorizeCorpusWorkflow` + `RevectorizeDocument` workflows, a
`list_documents_in_scope` activity (metadata query by `tag_ids` / `library_id` / `document_uids` /
`source_tag`), wiring the stub endpoint, and registering the two workflows in
`features/scheduler/worker.py`. Everything else is reuse.

## 4. Scope semantics
- `mode: full` → delete + re-embed every in-scope doc. `mode: incremental` → only docs with 0 vectors.
- `force: true` → ignore existing vectors, always re-embed. `embedding_model` → optional override
  (must match the index spec; otherwise the index `ensure_ready` mismatch guard applies).
- Migration default: scope = all migrated documents (e.g. by `source_tag`), `mode: full`.

## 5. Migration tie-in
The migration UI's final step ("Rebuild embeddings") calls `/corpus/revectorize` over the migrated
scope and renders the returned `task_id` with the **same** task atoms used by the import. Import
(control-plane) and re-vectorize (knowledge-flow) are two tasks in sequence; the cockpit shows both.

**This is the consumer of the importer's stage reset.** Per the dumb-export/smart-import contract
([`PLATFORM-IMPORT-RFC.md`](PLATFORM-IMPORT-RFC.md) → "Canonical contract"), the import resets each
migrated document's `VECTORIZED`/`SQL_INDEXED` stage to `NOT_STARTED` (vectors are never transported).
That flag is **inert until this workflow runs** — re-vectorize is what flips it back to `DONE`. The
two are two ends of one flow: a `NOT_STARTED` vector stage with no re-vectorize trigger is a lie.
Default scope for the migration run is therefore "all documents with `VECTORIZED != DONE`".

## 6. Risks / open items
- **Embedding model must match** what produced the original vectors for search parity (same model →
  compatible). Confirm the configured `embedding_model` on the target equals the source's.
- **Reuse of mirrored `output.md`**: re-vectorize should prefer the stored markdown output (cheap) over
  re-extracting from the raw input; confirm `output_process` takes that path when output exists.
- **Throughput**: 25 GB / thousands of docs — tune `max_parallelism`; embedding is the bottleneck.
- Task-queue choice: reuse `ingestion` vs a dedicated `reindex` queue (isolation vs simplicity).

## 7. Decision requested
Approve redesigning the stubbed `/corpus/revectorize` into the workflow above (reusing `output_process`
+ the task/event infra), tracked as MIGR-07, runnable standalone and as the migration's final phase.

## 8. Implementation note (2026-07-25)

Built as designed in §3-4; the open items in §6 resolved as follows, none of which change
the shape above:

- **Task queue (§6):** reused `ingestion` (simplicity — a dedicated `reindex` queue can be
  split out later if throughput isolation becomes a real problem).
- **Task `kind`:** the created `task_run` uses `kind="ingestion"` (`StartIngestionRequest`),
  not a new `kind="revectorize"` — the pseudocode's `task_service.start(kind="revectorize", …)`
  in §3 was illustrative. `emit_ingestion_task_event` is reused **verbatim** (per §2) and always
  emits `IngestionTaskEvent`; a task kind that didn't match would make `TaskService`'s terminal-
  event reconciliation (`_build_terminal_event`) emit the wrong event type. Adding a real
  `"revectorize"` kind would mean extending `TaskEvent`/`StartTaskRequest`/`TaskSummary.detail`
  in fred-core — out of proportion for what §3 calls "small" new code.
- **`max_parallelism`:** not a new request field on `RevectorizeOptionsV1` — reused the existing
  `scheduler.temporal.ingestion_workflow_parallelism` config already used to size the regular
  ingestion pipeline's `IngestionTaskService`.
- **Per-document failure handling:** `RevectorizeDocument` catches its own exceptions and returns
  `failed: true` rather than raising, so one bad document cannot abort the whole corpus batch —
  `RevectorizeCorpusWorkflow` always reaches a terminal `succeeded` event, with `failed` in
  `IngestionDetail` carrying the partial-failure count (same "succeeded with warnings" shape as
  `MigrationResult`, not a new terminal state).
- **`embedding_model` option:** stays advisory only (§6 risk, not a requirement) — not wired into
  `prepare_revectorize_file`; the original ingestion `profile` isn't recorded on `DocumentMetadata`
  either, so re-vectorize always uses `IngestionProcessingProfile.medium`.
- **Authorization gap fixed alongside:** `source_tag` was a real `CorpusScopeV1` field (needed for
  §4's migration-default scope) but wasn't accepted by the non-empty validator nor authorized in
  `corpus_manager_controller._authorize_scope`. Fixed: `source_tag`-only scopes now require
  `OrganizationPermission.CAN_MANAGE_PLATFORM` (same gate as `/documents/audit` and the
  import-export reset endpoints), since such a scope spans arbitrary teams.

`build_corpus_toc`, `purge_vectors`, and `/corpus/tasks/get|result|list` are untouched (still
mocked) — out of scope for MIGR-07.
