# Handoff: Robust library file-ingestion UX (kea `main`)

> **Working note, not for swift.** This change is kea-only, deliberately NOT to be
> merged to `swift` (swift has a different fred-core-based task/SSE system). Goal:
> make kea's "ingest files into a library folder" flow durable enough to buy the
> running production a month or two, with minimal, backward-compatible changes.

## Problem (what we fixed)
The old flow held a single streaming HTTP connection open for up to **30 minutes**
inside a modal bound to the upload drawer, uploaded files **one request per file
sequentially** (file N+1 didn't start until file N finished processing), and kept
all progress in **React state wiped on close**. Leaving the page = progress lost.

## Key architectural insight
kea's backend was already ~80% there: `/upload-process-documents` **persists each
document and submits the durable Temporal workflow BEFORE** entering its 30-min
poll loop. The metadata store (surfaced by the normal library browse endpoint via
`processing.stages`) is the durable source of truth. The fix is to **submit fast,
then let the library rows reflect backend status via polling** — no need to hold a
connection or remember a `workflow_id`.

## Design (what was implemented)
1. **New fire-and-forget backend endpoint** that persists + schedules and returns
   immediately (no poll loop). Existing streaming endpoint left untouched.
2. **Frontend submits via that endpoint in bounded batches of 20**, then closes the
   drawer immediately and refreshes the library.
3. **Library list polls** the browse endpoint every 3s while any visible doc is
   non-terminal (pending/processing), stopping when all are ready/failed. This is
   what makes "leave and come back / reload" work.
4. **A single status atom** (Pending / Processing / Ready / Failed) per row, derived
   from `processing.stages`; the old 5 per-stage pills moved into its hover tooltip.

## Files changed

### Backend — `knowledge-flow-backend`
- `knowledge_flow_backend/features/ingestion/ingestion_controller.py`
  - Added Pydantic models `ScheduledDocument` and `ScheduleDocumentsResponse`.
  - Added method `IngestionController._schedule_documents(...)` — mirrors
    `_stream_upload_process` persistence + the SAME `submit_documents(...)` batch
    call, but returns immediately. Robustness: per-file failures isolated;
    documents persisted before scheduling, so a submit failure marks files FAILED
    (no silent hang); memory/dev mode (no scheduler) processes inline so status
    stays truthful.
  - Added route `POST /knowledge-flow/v1/schedule-documents` delegating to it.
- `tests/features/ingestion/test_schedule_documents.py` (NEW) — 4 offline tests:
  scheduler-mode happy path + cleanup, per-file failure isolation, submit-failure
  marks files failed, memory-mode inline processing. All offline (no network).

### Frontend — `frontend`
- `src/utils/documentProcessingStatus.ts` (NEW) — single source of truth deriving
  overall status from `processing.stages`. Exports `getDocumentProcessingStatus`,
  `isDocumentProcessingTerminal`, `hasNonTerminalDocuments`. Mapping mirrors backend:
  ready = vector|sql done (`fully_processed`); failed = any stage failed & not ready;
  processing = any in_progress; else pending.
- `src/slices/streamDocumentUpload.tsx` — added `scheduleDocuments(files, metadata)`
  client (batches of 20, JSON response, per-batch try/catch so one bad batch can't
  lose the others). Types `ScheduledDocumentResult` / `ScheduleDocumentsResult`.
  Existing `streamUploadOrProcessDocument` left intact (still used by "upload" mode).
- `src/components/documents/libraries/DocumentProcessingStatus.tsx` (NEW) — status indicator.
  Pending/Processing/Failed render as a single chip (pills in hover tooltip); **Ready renders the
  familiar R/P/V/S/M pills inline** using the original muted pill palette (done = `#c8e6c9`/`#2e7d32`).
  Driven purely by `processing.stages`.
- `src/components/documents/libraries/DocumentLibraryRow.tsx` — replaced inline
  pills with `<DocumentProcessingStatus doc={doc} />`.
- `src/components/documents/libraries/DocumentUploadDrawer.tsx` — `handleAddFiles`
  now branches: **"process" mode → `handleScheduleFiles()`** (fire-and-forget,
  toast, refresh, close). **"upload" mode → unchanged** streaming path.
- `src/components/documents/libraries/DocumentLibraryList.tsx` — added a poll effect:
  while the open folder has non-terminal docs, re-`loadPage(currentTagId, 0, false,
  true, max(PAGE_SIZE, loadedCount))` every 3s; hard cap 20 min; auto-stops when all
  terminal (effect keyed on `hasPendingDocs`).

## Status: DONE + verified (checkpoint)
- Backend: `ruff check` ✅, `ruff format` ✅, `basedpyright` 0 errors ✅,
  `pytest tests/features/ingestion tests/services/test_ingestion_service.py` → **11 passed** ✅.
- Frontend: `npx tsc --noEmit` ✅ clean, `npx prettier --check` ✅ on all touched files.
- (Frontend has no flat-config ESLint wired in repo; `make` only runs prettier + tsc.)

## NOT done / next steps for the next instance
- **No live manual / e2e run** was performed (no running stack used). Recommended
  before shipping: upload ~50 files into a library folder, confirm they appear
  instantly as **Pending → Processing → Ready**, navigate away and back / reload,
  confirm status still updates. The `/verify` or `/run` skills can drive the app.
- **i18n**: new UI strings use inline English fallbacks via `t("key", "Default")`
  (matches existing `viewOriginalPdf` pattern). Optionally add real keys for
  `documentLibrary.statusReady|statusProcessing|statusPending|statusFailed`,
  `documentLibrary.scheduleQueuedSummary|scheduleQueuedDetail|scheduleFailedSummary`,
  `documentLibrary.uploadFailed` to the translation catalogs (en + fr).
- **OpenAPI client**: `scheduleDocuments` is a hand-written `fetch` (matching the
  existing `streamDocumentUpload` convention) — it is NOT in the generated
  `knowledgeFlowOpenApi.ts`. If you regenerate the client from the backend OpenAPI,
  you can optionally switch to the generated hook. Not required.
- The drawer still imports/renders `DocumentUploadProgressModal` for the legacy
  "upload" mode path; it is no longer used by the "process" path. Left in place for
  backward compatibility. Could be retired later if "upload" mode is dropped.

## Robustness hardening (round 2) — never "pending in fred but gone in Temporal"

Corner-case analysis identified two ways a doc could be stuck non-terminal forever:
- **A — Temporal unreachable at schedule time** (`submit_documents` throws): docs were
  persisted pending but never marked failed → Pending forever after reload.
- **D — worker down past the workflow's Temporal timeout**: workflow fails in Temporal
  but no activity updates metadata, and the `WorkflowTaskRecord` is worker-created so it
  doesn't exist → existing reconciliation finds nothing → Pending forever.

Root cause: the durable "this doc belongs to workflow X" link was only ever written by
the **worker**. Fix = write it from the **API**, and reflect Temporal's verdict on read.
No fred-side timeout/retry logic was added — we only mirror Temporal's own status.

Implemented:
1. **`Processing.workflow_id`** (new optional field, JSON blob → no migration) —
   [document_structures.py](knowledge-flow-backend/knowledge_flow_backend/common/document_structures.py).
2. **Pre-generated, race-free workflow id**: `_schedule_documents` generates `wf-<uuid>`,
   writes it on each doc **before** submit (so the worker inherits & preserves it — no
   clobber), and passes it through `submit_documents → start_document_processing →
   _register_workflow` (new optional `workflow_id` param threaded through base/temporal/
   in-memory schedulers).
3. **Scenario A fix**: on submit failure, each persisted doc is durably `mark_processing_failed`
   + re-saved (best-effort) → row shows **Failed**, not Pending.
4. **Scenario D fix — read-time reconciliation**: `IngestionService.reconcile_tag_processing`
   + `_reconcile_documents` (in [ingestion_service.py](knowledge-flow-backend/knowledge_flow_backend/features/ingestion/ingestion_service.py))
   and endpoint `POST /knowledge-flow/v1/documents/processing/reconcile`
   ([ingestion_controller.py](knowledge-flow-backend/knowledge_flow_backend/features/ingestion/ingestion_controller.py)).
   For each non-terminal doc with a `workflow_id`, one Temporal `describe` per distinct
   workflow (client call — works with worker down):
   terminal-failure/TIMED_OUT/CANCELED/TERMINATED → mark Failed (durable, best-effort persist);
   COMPLETED-but-not-done → mark Failed; RUNNING → leave; **None (Temporal unreachable) → leave
   (never false-fail on a transient outage)**. Persistence is best-effort: the response always
   reflects corrected status even if the viewer lacks write rights.
5. **Frontend**: new [reconcileProcessing.ts](frontend/src/slices/knowledgeFlow/reconcileProcessing.ts)
   helper; the library poll now calls `loadPage(..., reconcile=true)` which hits the reconcile
   endpoint **with automatic fallback to plain browse** if reconcile is unavailable.

Failure-mode coverage after hardening: A→Failed durably; B (flooded)→eventually consistent;
C (brief worker outage)→Temporal durability; D→Failed via reconciliation; E (activity error)→
already durable; F (Temporal server down on read)→left as-is, no false-fail.

Tests (all offline): `test_schedule_documents.py` now covers workflow_id-persisted-before-submit,
submit-failure marks+persists failed, the reconcile **decision matrix** (`_reconciled_failure_message`
for None/RUNNING/CONTINUED_AS_NEW/FAILED±error/TIMED_OUT/COMPLETED), `_is_processing_terminal`,
`_failure_stage`, and the reconcile **glue** (`_reconcile_documents`: fails dead workflows,
leaves running/unreachable, skips terminal/linkless). `test_scheduler_retry_policy.py` stub updated
for the new optional param. **44 passed** across the scheduler/ingestion/metadata sweep.

### Open follow-up (hardening)
- A full integration test of `reconcile_tag_processing` end-to-end (real metadata store +
  tagged docs via the conftest fixtures) would complement the unit/glue tests. The glue
  (`_reconcile_documents`) is unit-tested; the thin browse→glue wrapper is not.
- `ScheduleDocuments`/reconcile generated client: the user regenerated the OpenAPI client for
  `/schedule-documents`. **Regenerate again** to pick up `/documents/processing/reconcile`
  (currently called via the hand-written `reconcileProcessing.ts` fetch helper — works as-is).

## Security & authentication audit (new endpoints)

Both new endpoints were audited against the platform's two-layer model (coarse
`@authorize(Action, Resource)` + fine-grained ReBAC per tag/document).

- **Authentication**: both require `Depends(get_current_user)` (Keycloak). No anonymous access.
- **`/schedule-documents` (write)**: persistence goes through `save_document_metadata`, which
  enforces `rebac.check_user_permission_or_raise(user, TagPermission.UPDATE, tag_id)` for every
  target tag — identical to the existing upload endpoints. **Added hardening**: an explicit
  `ensure_can_write_tags(...)` fail-fast check at the top of the endpoint so an unauthorized
  upload returns **403 immediately** (via the global `AuthorizationError` handler) instead of
  running extraction / writing a raw-file blob and then failing per-file (which also avoids
  orphaned content-store blobs).
- **`/documents/processing/reconcile` (read + best-effort heal)**: listing uses
  `browse_documents_in_tag`, which **ReBAC-filters to docs the user can READ**. The heal-persist
  uses `save_metadata` → `save_document_metadata`, so it is independently gated by
  `TagPermission.UPDATE`; for read-only viewers the persist is denied and swallowed
  (best-effort), so they see the corrected status but cannot write. **Fixed**: the endpoint no
  longer wraps the call in `except Exception → HTTPException(500)`, which would have masked an
  `AuthorizationError` (403) as a 500 and leaked its detail. Exceptions now propagate to the
  global handlers (auth → 403, other → 500).
- **CSRF**: N/A — Bearer-token auth (no ambient cookie credentials).
- **Info disclosure**: failure messages (e.g. workflow last_error) are scoped to the requester's
  own readable documents; consistent with existing endpoints.

Tests added: `ensure_can_write_tags` checks `TagPermission.UPDATE` per tag and propagates denial.
Recommended follow-up: an integration test asserting 403 end-to-end for an unauthorized
schedule/reconcile against the real ReBAC engine (needs the conftest app-context fixtures).

## Deployment (per user's constraint)
Backward compatible. Restart only: **Knowledge Flow API** (serves the new endpoint
+ the UI bundle) and the **Knowledge Flow Temporal worker**. Assumes **no in-flight
Temporal tasks** at update time (explicit simplifying assumption — no migration
logic was added). Existing `/upload-documents`, `/upload-process-documents`, and
`/upload-process-documents/progress` endpoints are unchanged.

## How to re-run checks
```
# backend (from knowledge-flow-backend/)
VIRTUAL_ENV= ../fred-core/.venv/bin/uv run ruff check knowledge_flow_backend/features/ingestion/ingestion_controller.py tests/features/ingestion/test_schedule_documents.py
VIRTUAL_ENV= ../fred-core/.venv/bin/uv run basedpyright knowledge_flow_backend/features/ingestion/ingestion_controller.py tests/features/ingestion/test_schedule_documents.py
VIRTUAL_ENV= ../fred-core/.venv/bin/uv run pytest tests/features/ingestion -q --disable-socket --allow-unix-socket
# frontend (from frontend/)
npx tsc --noEmit
```
