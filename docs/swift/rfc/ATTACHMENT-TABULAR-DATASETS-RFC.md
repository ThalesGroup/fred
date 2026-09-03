# SQL-queryable CSV/Excel chat attachments

**Status:** Open — no implementation started. Follows and supersedes the
"not SQL-queryable" prompt guidance shipped in #2418/PR #2420, which was
explicitly scoped as a stopgap: *"Making fast-ingested CSVs real
session-scoped tabular datasets is a separate design change (RFC first) and
is intentionally not part of this issue."* This is that RFC.
**ID:** `ATTACH-TAB-01` (informal)
**Author:** Dimitri Tombroff / Claude Code
**Date:** 2026-09-03
**Related:** `docs/swift/design/DESIGN.md` §2 (Tabular Artifact & DuckDB
SQL-Mounting Contract, INGEST-06 — the machinery this RFC reuses),
`docs/swift/platform/PROCESSING_GUIDE.md` §3 (attachment fast-path registry),
issue #2418 / PR #2420 (the prompt-only stopgap this RFC extends beyond).

---

## 1. Problem statement

A user attaching a CSV (Excel next) to a chat conversation gets it processed
by `POST /fast/ingest` (`ingestion_controller.py:1049`): `FastLiteCsvProcessor`
renders a bounded Markdown table preview (20 rows × 10 cols / 60k chars
default) and stores it as ordinary text chunks in the shared vector store,
scoped by `user_id`/`session_id`/`scope="session"` metadata. No
`DocumentMetadata`, no Parquet artifact, no `tabular_v1` extension, no ReBAC
tuple is created.

For a question like "how many critical CVEs are in this file", that pipeline
is structurally unable to be reliable: the agent only ever sees a truncated
markdown table and must count/filter over retrieved text, which LLMs do not
do exactly. Fred already has a precise, production-grade answer to this exact
problem for corpus/library documents — CSV/Excel ingested into a team library
are converted to Parquet and made queryable through `/tabular/query`
(read-only DuckDB, ReBAC-authorized, execution-guardrailed; see `DESIGN.md`
§2). Attachments simply never enter that pipeline.

The user-visible failure mode already exists: agents holding tabular tools
try `get_tabular_documents_schemas` on an attachment uid and get a misleading
`403` (fail-closed ReBAC: an unauthorized document and an unknown document
look identical). #2418/PR #2420 papered over this with a prompt instruction
telling the agent to never try. This RFC proposes making the SQL path
actually work instead.

---

## 2. Proposed solution

**Scope for this RFC: CSV only (increment 1).** Excel/XLSX attachments keep
today's text-preview-only behavior until a follow-up increment generalizes
this design to `ExcelProcessor`'s multi-table output — noted in §6, not
designed here.

### 2.1 Reuse, not reimplementation

The Parquet-conversion and query machinery is untouched:

- `CsvTabularProcessor` (input: delimiter/encoding detection, DuckDB
  `read_csv_auto`) — already shared with the attachment path today via
  `FastLiteCsvProcessor`'s markdown-preview call.
- `TabularProcessor.process(file_path, metadata)` (output: CSV → Parquet via
  DuckDB `COPY`, writes `metadata.extensions["tabular_v1"]`) — reused as-is.
- `features/tabular/execution.py` guardrails (bounded concurrency, wall time,
  memory; `TabularService.query_read`/`search_read`) — reused as-is; a
  session-scoped dataset is mounted and queried exactly like a corpus one.

`TabularProcessor.process()` only needs a `DocumentMetadata` object in
memory to run — `Identity`/`SourceInfo`/`FileInfo` are plain Pydantic models,
not a database row, so building a throwaway one for an uploaded attachment is
mechanical (`document_uid` = the existing fast-ingest uuid, `source_type` a
new or repurposed value distinguishing it from corpus documents).

### 2.2 What's actually new

`fast_ingest` gains a CSV-specific branch: alongside (or instead of, see
open question in §5) the existing `FastLiteCsvProcessor` markdown preview, it
builds a `DocumentMetadata`, runs `CsvTabularProcessor` → `TabularProcessor`,
and ends up with a `tabular_v1`-bearing metadata object plus a Parquet
artifact in the content store, keyed the same way corpus tabular documents
are (`<artifacts_prefix>/<document_uid>/<source_revision>/data.parquet`).

Two things this metadata object needs that corpus documents get for free,
and that are the real design questions here (§5): somewhere for
`TabularService` to find `tabular_v1` at query time, and an authorization
answer that doesn't quietly re-introduce a ReBAC tuple for a document class
that was deliberately designed to have none.

### 2.3 Prompt suffix

`build_attachment_context_suffix` (`react_prompting.py`, just amended by
PR #2420) currently states CSV/XLSX attachments are "NOT loaded as
SQL-queryable tables." Once this ships for CSV, that line must flip to the
opposite instruction (pass the uid to the tabular tools) for `.csv` while
XLS/XLSX keeps the current stopgap wording until increment 2. The
per-line `_SPREADSHEET_ATTACHMENT_NOTE` annotation added in the same PR
needs the identical split. This is a direct, mechanical follow-up to code
merged into this branch — flagged so it isn't missed as "someone else's
prompt text."

---

## 3. Alternatives considered

- **Lightweight session-scoped DuckDB mount, no persisted artifact or
  `DocumentMetadata` at all** (mount the uploaded CSV file directly per
  query, discard after). Rejected as the primary design here because the
  developer directed reuse of the full tabular pipeline (this RFC, "approach
  1"); noted as the faster-to-ship fallback if §5's authorization question
  proves harder to close than expected.
- **Code-execution/pandas sandbox tool** instead of fixed SQL. More flexible
  for irregular real-world CSVs and for the per-row analysis the user
  mentioned as a likely next topic, but a materially larger security/sandbox
  surface. Deferred — revisit only if SQL-over-Parquet turns out not to
  express the per-row analysis need once that work starts.
- **Generalize `tabular_v1` and `tabular_multi_v1` into one schema** to cover
  attachments and corpus uniformly. Rejected per `DESIGN.md`'s existing
  decision (§2): CSV vs. spreadsheet already deliberately stayed two keys to
  avoid migrating ingested documents; adding a third axis (attachment vs.
  corpus) to the same keys would compound that, not simplify it. An
  attachment-owned `tabular_v1` document is a new *document*, not a new
  schema variant.

---

## 4. Impact on existing contracts

| Contract file | Change |
|---|---|
| `RUNTIME-EXECUTION-CONTRACT.md` | Attachment-uid-to-tabular-tool behavior changes for `.csv` — needs a dated §8 entry once implemented. |
| `DESIGN.md` §2 | If `TabularService` gains a second, non-ReBAC authorization branch (§5), that's a documented exception to "document-level ReBAC decides visibility" and must be added there, not silently diverge from it. |
| Attachment API (`FastIngestResponse`) | Likely needs a field signaling "this attachment is also a queryable dataset" (e.g. echo whether `tabular_v1` was produced) so the frontend/agent can reflect it — exact shape TBD at implementation time. |

---

## 5. Open questions (why this is still an RFC)

- **Authorization model — the central open question.** Fast-ingested
  documents are deliberately "resource-less": no ReBAC tuple, ownership
  proven via vector-chunk metadata instead
  (`_authorize_fast_ingest_delete`, `ingestion_controller.py:112-121`).
  `TabularService._resolve_authorized_datasets` is currently 100%
  ReBAC-driven. Two ways to close this gap, neither implemented yet:
  1. Mint a real (deletable) ReBAC tuple scoping the document to its
     uploader/session at fast-ingest time — reuses `TabularService`'s
     existing resolution path unmodified, but reverses the deliberate
     "resource-less" design and adds a tuple that must be deleted in lockstep
     with the vectors and the Parquet artifact.
  2. Add a second, ownership-metadata-based authorization branch to
     `TabularService`, mirroring the pattern `_authorize_fast_ingest_delete`
     already uses for deletion — consistent with the existing design
     decision, but means `TabularService` no longer has one uniform
     authorization story for every dataset it serves.
  This needs a decision before implementation starts, not during it.
- **Where does `tabular_v1` metadata live for `TabularService` to find at
  query time?** Corpus documents persist `DocumentMetadata` in a metadata
  store `TabularService` already reads from. A session-scoped attachment has
  no such persisted row today. Options: write into the same store with a
  `scope=session` marker (naturally found, but now that store holds
  ephemeral rows it must also clean up), or a separate lightweight
  session-document registry. Whichever is chosen must be deleted by
  `_delete_fast_ingest_artifacts` alongside vectors and the Parquet artifact
  — today that function only deletes vectors, and would silently orphan the
  new artifact/metadata/tuple otherwise.
- **Does the CSV attachment keep its existing markdown-preview text chunk in
  addition to becoming a tabular dataset, or does the tabular path replace
  it?** Both narrative summarization ("what's in this file") and precise
  querying ("how many critical CVEs") are legitimate asks on the same
  attachment — leans toward "both," but is a real product choice, not purely
  technical.
- **Dataset-pointer chunk** (`TabularProcessor._emit_pointer_chunk`, default
  off): it exists to solve semantic-search discovery for corpus documents an
  agent doesn't otherwise know exist. An attachment's uid is already handed
  to the agent directly in the prompt suffix, so the discovery problem the
  pointer chunk solves may not apply here — leans toward leaving it off for
  attachments regardless of the global corpus setting, but worth confirming
  rather than assuming.
- **TTL / expiry semantics.** Corpus tabular datasets are permanent until
  explicitly deleted. Session-scoped attachment datasets should presumably
  not outlive their session/conversation (matching how fast-ingest vectors
  are already cleaned up by the control-plane lifecycle worker per
  `_authorize_fast_ingest_delete`'s docstring) — needs the same lifecycle
  hook extended to cover the new artifact/metadata/tuple, not a new
  independent expiry mechanism.

---

## 6. Out of scope

- **Excel/XLSX attachments (increment 2).** Same shape via `ExcelProcessor` +
  `ExcelTableRegistrationProcessor`'s multi-table (`tabular_multi_v1`)
  output, deferred until increment 1 (CSV) ships and its authorization/
  lifecycle answers are proven — those answers should transfer directly, but
  re-verify rather than assume, per the `tabular_multi_v1` per-table alias
  scheme's added complexity (`DESIGN.md` §2).
- **Code-execution/pandas analysis tool** for the "per-row analysis" follow-up
  work the user flagged as a likely next topic. Explicitly a separate,
  larger design once the SQL path's limits are actually hit in practice.
- **Any change to corpus/library tabular ingestion.** This RFC only extends
  *who* can produce a `tabular_v1` artifact (attachments, in addition to
  corpus ingestion) — the artifact format, DuckDB mounting, and execution
  guardrails are unchanged.
