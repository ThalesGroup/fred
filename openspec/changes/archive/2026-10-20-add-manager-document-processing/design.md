## Context

See [proposal.md](proposal.md) for scope. Discovery base: `b50e5217a`, clean
`chore/rust-rebac`, including original storage commit `3a39c4eb5`.

| Existing implementation | Reuse and required change |
| --- | --- |
| Manager `documents/upload.rs`, `document`, `document_upload` | Verified immutable original and two guarded publication boundaries already exist; add processing intent to the publication transaction. |
| Manager `lifecycle/worker.rs` | Rust Temporal client and separate worker process already exist; reuse connection conventions, not the space-deletion workflow. HTTP startup must remain independent of Temporal availability. |
| KF `scheduler/workflow.py`, `worker.py` | Common orchestration/indexing and fast/medium/rich extraction queues already exist. Keep ProcessPush, PipelineDefinition/FileToProcess and the existing activity signatures unchanged. |
| KF `push_files_activities.py`, `activities.py`, `ingestion_service.py` | Currently depend on Python metadata, tag authorization, content layout and task rows. Add an explicit manager storage/authority adapter at these existing activity boundaries. |
| KF `extraction_process.py`, pipeline manager and output processors | Reuse process supervision, extractors, splitters and embeddings. Add explicit storage/output dependencies where processors currently reach through the global application context. |
| KF `content/content_service.py::get_pdf_render` and frontend `documentViewerUtils.ts` | Office native PDF previews are currently rendered on demand by the KF HTTP API, outside ingestion. Move that computation into the manager document's worker execution and rebind both File and Raw preview sources. |
| Frontend `DocumentUploadDrawer`, `managerImportRun`, `useManagerImports`, `managerDocuments` | Existing manager bindings force upload-only and project every stored receipt as succeeded. Restore mode/profile and bind processing/preview to manager. |

The current `document-storage` specification explicitly forbids ingestion in the
Resources journey; its UI requirement must change, while the independent storage
guarantees remain. `simplify-corpus-authorization` covers broader retrieval and
conversation migration. This slice does not implement that backlog or the external
provider SDK in #2240. Arc42 is the branch authority for manager; older Python
platform documents do not override its organization/space model.

## Goals / Non-Goals

Build the complete accepted-document-to-published-result path, including recovery
and UI observability, using one document identity. Keep authoritative state in
manager and computation in KF workers. Neither a serialized user object nor a
queue message is authorization. Scope exclusions are in the proposal.

## Decisions

### 1. Durable admission and direct Temporal dispatch

Extend the existing upload query with a typed processing choice (upload-only or
process with an explicit fast/medium/rich profile). The UI restores its existing
process/fast defaults; omitted API choice retains upload-only. Bind the choice to
the upload idempotency record, including retry comparisons. Commit the document,
stored receipt and initial pending processing row together. Invalid/disabled
processing choices fail before accepting bytes; a runtime Temporal outage does
not undo a verified upload or lose its processing intent.

Reuse `document_upload` for transfer receipts and `document` for current result
identity. Add one `document_processing` table for processing attempts, with an
actor-scoped request key, document/space/original digest, selected profile,
workflow ID, delivery lease/backoff, stage/status/revision, bounded error, timestamps,
stage fencing data and result manifest reference. A partial unique constraint
permits only one active processing attempt per document. This table also supplies
dispatch recovery; no additional outbox table is needed. Extending upload receipts
alone would incorrectly couple every later processing attempt to a byte transfer;
the Python `task_run` schema has legacy team ownership and a different database
owner, so it is not reused as manager authority.

Run bounded SQL delivery/reconciliation in the existing manager worker process,
independent of lifecycle enablement. Claim a batch briefly, release SQL locks,
then start the existing `ProcessPush` on KF's configured common queue with a
deterministic workflow ID containing the installation namespace and processing ID.
Use duplicate rejection for running AND closed workflows. Lost start acknowledgments
are resolved against that ID, never by generating another one. A stored delivery
acknowledgment prevents re-dispatch after Temporal history retention expires.
Ambiguous expired history is an explicit failed/unknown delivery outcome requiring
reconciliation, never evidence to start again. No network call holds a SQL claim lock.

The manager worker must reconnect after Temporal outages without blocking HTTP
startup. Explicit execution and queue-wait deadlines bound missing consumers; SQL
reconciliation expires overdue accepted work within the admission-bounded active
set and retains the last stage; delivery claims use bounded pages. Temporal termination without a persisted result becomes failure, not
success. SQL and Temporal are not treated as one atomic transaction.

### 2. Existing Knowledge Flow worker contract, unchanged

Developer clarification on 2026-10-19: preserve the Knowledge Flow worker contract
identically and avoid a parallel ingestion implementation. The Temporal payload is
exactly the existing `PipelineDefinition` containing `FileToProcess`; the workflow
is `ProcessPush`, with its existing children and activity signatures. Python's
existing Pydantic models remain the schema authority. Rust submissions are tested
by decoding with those models, not by inventing a replacement schema.

Extract the current submission-policy calculation into one shared Python helper.
Export its resolved fast/medium/rich fields alongside the worker schema from the
KF deployment configuration. Manager consumes that generated configuration and
persists the exact submission payload with the attempt. All existing timeout and
retry fields, including metadata timeout and non-retryable error types, retain
their meaning. Manager does not introduce a second policy catalog.

Use the existing source_tag locator to identify one immutable manager installation
and processing attempt. tags stays empty and task_id stays null: there is no legacy
tag, metadata or task authority. processed_by retains its required KeycloakUser
shape with the accepted actor's UID and no asserted privileges or token. It is
informational; manager checks the recorded actor and current rights independently.
The existing DocumentMetadata result carries the same source locator between
activities. No new workflow or alternative CSV/Excel pipeline is introduced.

Adapt persistence at the existing metadata, input and output activity boundaries.
Propagate explicitly scoped dependencies into restoration, subprocess extraction
and the configured output processors. Reuse the existing category routing,
processor classes, splitter, embeddings and tabular behavior. Never replace a
process-global singleton for a concurrent activity. The manager worker protocol
for claims, manifests and publication is internal persistence integration, not a
replacement for the Temporal worker contract.

ProcessPush can complete normally with failed child documents. Manager never
infers processing success from COMPLETED alone; only verified publication can
succeed. Per-activity failures release their fenced stage attempt while retaining
the existing Temporal retries. Final workflow reconciliation records exhaustion.

### 3. Workload authentication and scoped artifact access

Extend manager authentication with a dedicated worker extractor, using the existing
OIDC/JWKS and factory service-account conventions. Require signature, issuer,
manager audience, allowed workload client and service-account identity. Human JWTs,
platform roles and arbitrary headers cannot select this path. Provision credentials
and rotation through factory/chart secrets, never through Temporal payloads.

Worker-only routes under manager's document-processing resource load the accepted
operation and validate installation, document, original digest, current stage and
fence. They provide the descriptor, streamed original, stage claims, bounded progress
and publication. Original reads use the recorded actor's current admission,
organization context and effective Write permission. Final successful publication
repeats those checks under the existing organization guard. A user's access token
is not retained for asynchronous work; its expiry is distinct from role/CGU
revocation. A revoked initiating actor cannot publish results. An authorized current
editor may later start a new attempt under their own identity.

Progress/failure recording authenticates the worker and exact operation/fence but
does not require the former actor to retain Write: otherwise revocation would leave
the row running forever. These updates cannot publish content or alter scope.
All public status/result/preview reads use the caller's current space Read policy;
processing starts/retries require Write. Administration alone confers neither.

Workers receive no credentials for manager originals or direct SQL access. Fetch
the original through manager using bounded streaming and validate size/SHA-256
before extraction. Derived files use a separate, installation-scoped storage
namespace with worker credentials restricted to derived data. Manager owns the
publication manifest and serves only its allowlisted outputs through authorized
document endpoints; a caller cannot supply an arbitrary object key or URL.

### 4. Fenced output and one publication boundary

Each activity execution claims a server-issued, expiring stage generation; retries
and duplicates use conditional SQL transitions. Outputs and vector/table records
are scoped by installation, organization, space, document, processing ID and stage
generation. A timed-out worker can only finish into its obsolete generation.
The next stage consumes the exact committed predecessor manifest. A conditional
manifest commit admits only the current generation, with the original digest and
current stage generation. Replay of the same commit returns the stored result; a different
manifest under that key conflicts. Late progress cannot regress a stage or overwrite
a terminal result. Validate manifest paths, sizes, digests, artifact types and counts
against durable output before marking success.

Use the existing vector/tabular adapters with injected manager-specific stores or
namespaces and deterministic generation-scoped IDs. Preserve manager scope fields
through metadata sanitization. Legacy KF search, listing, previews, PDF expiry and
corpus repair must never discover or mutate these stores. A metadata flag alone
on the legacy index is insufficient isolation. Successful processing means actual
derived output/index persistence, not that migrated chat retrieval is available.

Bound attempts, local spool/output bytes, manifest size, chunk batches, pending
admission and cleanup backlog. Keep the existing original quota charge once;
derived data has a separate configured capacity budget. A periodic bounded worker
cleanup removes abandoned generations and partial vector/table output, with its
own retries. Retain publication references and fences until cleanup is confirmed;
repeated scans catch late writes. SQL/manager unavailability prevents acquiring destructive cleanup authority.
Originals and published objects/chunk ordinals remain protected. A published
generation with unused adaptive-indexing ordinals can be swept only for those
unused IDs; its manifest objects and published IDs are retained.
Independent original-storage cleanup must exclude the derived namespace explicitly.

### 5. Public API and existing UI

Extend manager's existing document surface: POST document processing for an already
stored original, GET processing history/current result, and authenticated preview
content referenced by the published manifest. Generate OpenAPI and RTK clients.
Return typed processing summaries with directory/documents and upload receipts,
avoiding one status request per displayed document.

One import row follows upload then processing. Keep `stored` as transfer success;
processing uses the existing pending/running/succeeded/failed UI vocabulary and
queued/preparation/extraction/indexing stages, indeterminate progress where no
measurement exists. Persisted manager state is authoritative. Extend the existing
bounded receipt polling and document refresh; do not add an SSE service or duplicate
Python task journal for this slice. Rehydrate across reloads and isolate account/
organization changes. Acknowledging an upload cannot hide active processing.

An editor can process a stored-only document and explicitly retry a failed attempt
without uploading bytes or charging original quota again. Bind idempotency to the
document/digest/profile; concurrent matching starts resolve to one active attempt,
conflicting choices return 409. A retry uses a new key linked to the failed attempt,
and at most one successor wins. This lot does not reprocess successful documents.
Keep user cancellation unavailable, matching current ingestion semantics. Failures
retain safe stage/error information and leave original download available. Reuse
the existing preview renderer and artifact loading protections; expose no active
HTML, arbitrary external fetch or unsafe attachment content through preview.

For PDF input, File preview streams the verified original through a separately
authorized, bounded PDF/range response; the download endpoint retains attachment
semantics. For Office formats currently accepted by `PDF_RENDERABLE_SUFFIXES`
(`.docx`, `.doc`, `.odt`, `.pptx`, `.ppt`), the extraction worker also calls the
existing office-to-PDF converter (or retains its already produced PDF) and saves
that native render in the fenced output manifest. Run conversion within the
same supervised resource/deadline envelope; include the existing LibreOffice
dependency in worker validation. Raw preview reads the extracted Markdown/assets.
Both sources are manager URLs; preserve the existing File/Raw controls and defaults.
The native PDF is a required output for those formats in this slice: exhausted
conversion failure fails processing at preparation/extraction with a safe preview
error and retry from the original. Do not publish partial success with a broken
default File tab. This intentionally moves cold-render failure from first viewing
to processing for manager-owned documents; legacy documents retain their existing
behavior. A published native render lives with the published result and is not
subject to the legacy on-demand PDF cache expiry job.

### 6. Authorization costs and verification budgets

Use the actual `L` placement Reads and `Q(actor)` organization-context Reads in
arc42 chapter 9, not the unimplemented `one-check-per-request` proposal. All Reads
are paginated to completion; exact parent/organization/version filters and
`HIGHER_CONSISTENCY` follow the current manager helpers.

| Operation | Proposed incremental/current FGA budget | SQL/network ordering |
| --- | --- | --- |
| Upload with processing | Same existing upload budget: `3*(L+Q)+2` Reads, 3 Write-permission Checks, 2 guard Writes with 2 tuple operations each | Add intent within the already authorized publication transaction; no Temporal/storage IO inside it. |
| Explicit processing start/retry | `L+Q+1` Reads, 1 Write-permission Check, 1 guard Write with 2 tuple operations | Resolve placement, acquire org lock, guard Read/context/Check/fence, insert attempt, commit. |
| Worker preparation claim/original access | `L+Q` Reads and 1 Write-permission Check per authorized access | Workload validation and SQL identity binding first; no SQL transaction across byte streaming or processing. |
| Final successful publication | `L+Q+1` Reads, 1 Write-permission Check, 1 guard Write with 2 tuple operations | Verify staged outputs outside the lock; guarded authority and conditional manifest reference commit inside it. |
| Document/status/preview read | `L+Q` Reads and 1 Read-permission Check; directory retains its existing 2 Checks | One space decision for a bounded page, never one decision per document or chunk. |
| Dispatch, later stage claims, progress/failure, reconciliation | Zero FGA calls | Trusted work identity and SQL state checks; these cannot grant access or publish success. |

No document/folder/chunk role tuples, `ListObjects`, `ListUsers`, `Expand` or
`BatchCheck` are introduced. Membership pages and space depth drive authorization
cost; document count drives SQL pagination and chunk count drives computation and
index writes. Client RPC counts do not measure server evaluation. Measure guards,
tuple volume and SQL lock duration with fixtures of 1/100 documents, bounded large
memberships and concurrent starts/publication/revocation; record actual figures
and any justified change to these proposed budgets before close-out. The final
measured inventory and sampling limits are in arc42 chapter 9. Start additionally
loads the space before entering the shared write guard, so its test fixture uses
six Reads versus five at final publication. Preparation claims also check actor authority;
they are not part of the zero-FGA dispatch/progress budget.

## Risks / Trade-offs

- Existing processors reach global stores: inject only the dependencies used by
  this second owner; prove legacy behavior and reject shared-index configuration.
- A Temporal timeout does not kill every Python thread: generation isolation and
  conditional publication fence its effects even after physical work overlaps.
- Worker or manager outage can delay progress: retain monotonic SQL state, bounded
  reconciliation and explicit queue/execution deadlines; never infer success.
- Original integrity, extraction, model, index and publication are separate failure
  points: classify safe non-retryable failures versus transient retries, and test
  recovery through real Temporal and the adapter boundaries through focused fault
  fixtures. Record those proof levels separately. Do not copy raw exception text
  into user errors.
- This is a substantial feature across two languages: complete the contract fixture
  and minimal real-worker text/PDF vertical first, then cover all profiles/formats
  and failure cases before declaring the lot ready. These are internal tasks, not
  independently shippable partial behavior.

## Migration Plan

After scope confirmation, implement on `chore/rust-rebac` without pushing. Edit the
single manager baseline and reset only the explicitly selected disposable local
installation; inventory existing data and document the destructive reset procedure
before executing it. Never reset an unrelated running installation to run tests.

Configure manager dispatch, KF worker contract support, strict M2M identity,
separate derived/index stores, bounded budgets and shared Temporal namespace/queue
in local YAML and chart values with regenerated schemas. Worker profile settings
remain canonical in KF. Processing can be disabled to retain upload-only operation;
do not silently fall back to KF HTTP or an in-memory scheduler. Drain accepted work
before removing support or changing queue/contract versions. Rollback stops new
processing, fences/reconciles existing attempts and keeps originals downloadable;
old manager binaries require a matching baseline/database, not an implicit downgrade.

Validate backend contracts and the existing UI with the KF HTTP API stopped. Run
manager unit/integration/quality checks, targeted KF/Temporal and frontend tests,
root quality checks, required independent review and correction review. Update
arc42 only for implemented behavior, regenerate derived blocks, add the branch
migration note, validate/sync/archive OpenSpec, and commit the complete verified
step locally. No production sizing claim follows from the functional fixtures.
