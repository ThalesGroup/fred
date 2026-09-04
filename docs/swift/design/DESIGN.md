# 📐 DESIGN.md – Ingestion Pipeline Structures

This document describes the design of core data structures in the Fred ingestion pipeline, with a focus on **when** and **why** they are used.

---

## 🧭 Push vs Pull Documents

Fred supports two ingestion modes:

### ➕ Push Documents

- The user **uploads a document** (e.g., PDF) through the API or UI.
- A `document_uid` is assigned immediately.
- A `DocumentMetadata` is created and saved **immediately**.
- The document is stored and retrievable from the backend.

> Push files always have `document_uid` and a stored metadata record.

### 📥 Pull Documents

- Represent **external files** (e.g., on disk, Git, or WebDAV).
- Initially discovered as `PullFileEntry` objects via catalog scan.
- Only when the user explicitly triggers processing is a `FileToProcess` created.
- **No metadata is stored until processing begins**.
- During processing, a virtual `DocumentMetadata` is generated and then persisted.

> Pull files have no metadata until the user triggers ingestion.

---

## ⚙️ Ingestion Mechanisms

Fred supports two ingestion entry points:

### 1. 🧩 Temporal-based Pipeline (recommended)

- Activities:
  - `extract_metadata_activity`
  - `process_document_activity`
  - `vectorize_activity`
- Supports staged, recoverable, asynchronous workflows
- Can be triggered manually or programmatically (via pipeline definitions)

> Unified handling of push and pull through `FileToProcess`.

### 2. 🚀 Direct Controller-based Ingestion

- REST endpoint accepts uploads and optionally processes immediately
- Used for fast/manual ingestion
- Still relies on the same structures (`DocumentMetadata`, etc.)

> Ideal for small uploads or test tools; same design structures apply.

---

## 🧱 Core Structures

### 1. `PullFileEntry`

**What**: Discovered file in a pull source (e.g., `/mnt/docs/report.pdf`)

**When**: Returned during catalog scan

**Why**: Transient structure used to let the user select a file to ingest

```python
class PullFileEntry(BaseModel):
    path: str            # Relative path in pull source
    size: int            # File size in bytes
    modified_time: float # Unix timestamp (mtime)
    hash: str            # Path-based stable hash (used for UID)
```

---

### 2. `FileToProcess`

**What**: Describes a document to be ingested

**When**: Created when user triggers ingestion (UI or API)

**Why**: Primary input to both the ingestion controller and Temporal pipeline

```python
class FileToProcess(BaseModel):
    source_tag: str
    tags: List[str] = []

    # Push
    document_uid: Optional[str] = None

    # Pull
    external_path: Optional[str] = None
    size: Optional[int] = None
    modified_time: Optional[float] = None
    hash: Optional[str] = None

    def is_push(self) -> bool
    def is_pull(self) -> bool
    @classmethod
    def from_pull_entry(...)
    def to_virtual_metadata(...) → DocumentMetadata
```

> Ingestion logic only needs this class as input.

---

### 3. `DocumentMetadata`

**What**: The master record of a document’s metadata and ingestion state

**When**:

- Created immediately for push files
- Created virtually during pull ingestion, and saved after processing begins

**Why**: Tracks document identity, source, status, and metadata for retrieval and UI display

```python
class DocumentMetadata(BaseModel):
    document_name: str
    document_uid: str
    date_added_to_kb: datetime
    retrievable: bool

    # Pull-specific fields
    source_tag: Optional[str]
    pull_location: Optional[str]
    source_type: SourceType  # Enum: PUSH or PULL

    tags: Optional[List[str]]
    title, author, created, modified, etc.

    processing_stages: Dict[ProcessingStage, Literal["not_started", "in_progress", "done", "failed"]]

    def mark_stage_done(...)
    def set_stage_status(...)
    def is_fully_processed(...) → bool
    def get_display_name(...) → str
```

> This object lives in the metadata store and is the main UI reference.

---

## 1. Spreadsheet Ingestion Pipeline (INGEST-02)

Excel workbooks (`.xlsx`/`.xls`/`.xlsm`) are ingested as a new `spreadsheet`
document category, disjoint from `tabular` (CSV): `PREVIEW_READY` (writes
`output.md`) and `SQL_INDEXED` (registers tables), but **never vectorized** —
`is_spreadsheet_file()` gates the scheduler so chunk-embedding of tabular data
never happens.

**Pipeline shape — `ExcelExtractor`, phases A/B, five steps each:**

- **A1** inventory (sheet triage map) → **A2** load with `data_only=True`,
  capture merges/outline levels/error cells/hidden rows-cols → **A3** detect
  tables via 4-connectivity connected components (≥2×2, ≥4 non-empty cells,
  else residual) → **A4** split vertically-stacked tables sharing one island
  (full-width merged row = new title) → **A5** strip leading label columns
  (a column whose single vertical merge covers ≥80% of body height).
- **B1** orientation (`normal`/`transposed`/`cross-tab`, auto-straightened via
  `df.T`) → **B2** to DataFrame (merged cells auto-filled from anchor, first
  row = header) → **B3** drop fully-empty rows/columns → **B4** clean & coerce
  (dates → datetime; numeric **recognized but not converted** — thousands
  whitespace stripped, currency/%/decimal-comma kept as string; text
  trimmed) → **B5** validate & tag (provenance: file, sheet, range, title,
  orientation).
- **Not built:** multi-level header reconstruction, unpivot-to-long, LLM
  vision fallback (pipeline is deterministic-only — a table that fails A/B is
  marked `status="failed"` and recorded as residual), `.xls` via `xlrd`,
  formula preservation, formatting-as-data extraction.
- **LibreOffice headless recalculation** (`recalc_with_libreoffice`) is
  opt-in for `.xlsx`/`.xlsm` and **mandatory** for legacy `.xls` (openpyxl
  cannot read binary BIFF) — this is how `.xls` support actually shipped,
  not via `xlrd`.
- **Display-fidelity masking** — values hidden by Excel number format, zeros
  hidden by `showZeros=False`, and error cells are all treated as empty, so
  extraction matches what a human sees on screen.
- **Empty sheets are reported, not skipped** — a sheet holding no value
  (blank, or carrying only styles/merges/column widths) short-circuits after
  A2: phases A3–B5 are skipped and `output.md` names it
  `## Sheet: <name>  (visible, empty)` with an explicit "No data" line, so a
  reader can tell an empty sheet from one extraction lost. It contributes no
  `tables.json` entry.
- **Export** writes one Parquet per non-empty table + a `tables.json`
  sidecar (per table: `table_id`, `sheet`, `title`, `range`, `data_range`,
  `format`, `path`, `row_count`, `columns`, plus `object_key`/`query_alias`
  in ingestion mode) + `output.md` (human/LLM-facing catalog with a coverage
  metric per sheet). `tables.json` is the contract the output stage
  (`ExcelTableRegistrationProcessor`) promotes into `tabular_multi_v1` (§2).
  A missing sidecar is a warning (empty result); a malformed one is a hard
  `TabularProcessingError`. Residual values are spreadsheet text injected into
  a Markdown bullet: multi-line values are indented under their item with hard
  line breaks and their leading block markers (`-`, `#`, `1.`, …) escaped, so
  a cell never spawns bullets of its own.

**Code map:** `core/processors/input/excel_processor/excel_extractor.py`
(`ExcelExtractor`, phases), `excel_processor.py` (`ExcelProcessor`, I/O +
LibreOffice recalc), `core/processors/output/excel_processor/
excel_table_registration_processor.py` (output stage).

**Tabular value locator (`search_tabular_values`):** a read-only
`POST /tabular/search` tool scans every column of every table of the
requested documents for a normalized substring match (lowercase, strip
accents, remove whitespace, comma→point) and returns, per matching table,
the matched columns and a bounded sample of rows — so an agent can locate
*which* table holds a value before issuing one targeted `read_query`,
instead of brute-forcing `read_query` table by table. Reuses the same
resolve → select → mount → redact path as `read_query`, so ReBAC and
signed-URL redaction are identical. `max_rows_per_table` (default 5) and
`max_matching_tables` (default 30) bound the response; both truncation
signals must be surfaced to the agent.

## 2. Tabular Artifact & DuckDB SQL-Mounting Contract (INGEST-06)

Two ingestion producers — the CSV path (one document → one table) and the
spreadsheet path (§1, one workbook → N tables) — share one spine that turns
ingested tabular data into an agent-queryable, read-only SQL surface.

**Metadata contract** — stored in `DocumentMetadata.extensions`, versioned
in-band (not a frozen platform contract):

- `tabular_v1` (`TabularArtifactV1`, CSV, single table): `dataset_uid`,
  `object_key`, `source_revision` (document `sha256`), `format="parquet"`,
  `row_count`, `columns` (`TabularColumnSchema{name, dtype}`), `generated_at`,
  `file_size_bytes`.
- `tabular_multi_v1` (`TabularMultiArtifactV1`, spreadsheet): holds
  `tables: list[TabularTableArtifactV1]`, each **extending** `TabularArtifactV1`
  with `query_alias` (the exact SQL relation name — stored, must match
  `output.md`), `sheet`, `table_id` (`<sheet>.tN`), `title`, `range`/`data_range`.
  Two keys, not one generalized key, deliberately — generalizing CSV to a
  one-element `tabular_multi_v1` was rejected to avoid migrating already-
  ingested documents.
- `DTypes = Literal["string","integer","float","boolean","datetime","unknown"]`
  — one stable vocabulary independent of pandas or DuckDB internals; both
  producers converge on the same `TabularColumnSchema` shape.

**Object-store layout** — content-addressed, under
`storage.tabular_store.artifacts_prefix` (default `tabular/datasets`):

```
<artifacts_prefix>/<document_uid>/<source_revision>/data.parquet        # tabular_v1  (CSV)
<artifacts_prefix>/<document_uid>/<source_revision>/<Sheet.tN>.parquet   # tabular_multi_v1 (one per table)
```

`source_revision` is the document `sha256`, so a re-ingested revision writes
to a fresh path; every table of a workbook shares the per-document prefix,
so revision cleanup is one `list_objects` + prune for CSV and spreadsheet
alike.

**SQL alias scheme — determinism is the contract.** The relation name an
agent types in SQL must equal the mounted name **and** the name the producer
advertised (`output.md` or a dataset listing):

- CSV: `build_default_query_alias(uid, name)` → `d_<uid12>_<stem>`.
- Spreadsheet table: `build_table_query_alias(uid, sheet, index)` →
  `d_<uid12>_<sheet>_t<N>` — the per-sheet index is part of the name because
  one sheet can hold several tables.
- The spreadsheet stage stamps `query_alias` into `tabular_multi_v1` and
  prints the same value in `output.md`; the resolver reads the stored alias,
  it never re-derives it. `_claim_alias` only guards the theoretical
  cross-document collision (two documents mounted in one query): it renames
  and **logs a warning** — the one sanctioned, observable divergence.

**Resolution & DuckDB mounting** (`TabularService`):

1. **Resolve** — for each ReBAC-authorized document, `tabular_v1` → one
   `ResolvedDataset`; `tabular_multi_v1` → one `ResolvedDataset` per table.
   Authorization is checked once at document level; expansion to tables
   happens after.
2. **Select** — a `/tabular/query` request naming a workbook uid mounts
   **all** of that workbook's tables.
3. **Mount** — a fresh in-memory DuckDB connection **per query** mounts only
   the caller's readable datasets as read-only views over Parquet. No
   cross-query state, no writable tables.
4. **Locate** — remote object stores resolve Parquet through a short-lived
   backend-internal presigned URL (§3), read via DuckDB `httpfs`; local
   filesystem storage uses a direct path. A store offering neither fails as
   an explicit unsupported operation.
5. **Redact** — signed URLs are stripped from any caught `duckdb`/`httpfs`
   error before it is logged or surfaced.

The runtime is **read-only DuckDB over Parquet** — not a SQLAlchemy layer
over PostgreSQL/MySQL/SQLite.

**Authorization model:** document-level ReBAC decides visibility; table-level
SQL exposure is a projection of that decision — once a document is
authorized, every one of its tables is mountable (a workbook is one
authorization unit, no per-table authorization).

**API surface** (document-centric, INGEST-04): `GET /tabular/documents` (one
row per document, `kind: "csv"|"spreadsheet"`, no columns — light for LLM
context), `GET /tabular/documents/schemas?document_uids=…` (batch, **all**
tables of each document with full `columns[]`), `GET
/tabular/documents/{uid}/markdown` (a spreadsheet's `output.md`, 404 without
`tabular_multi_v1`), `POST /tabular/query` (read-only SQL). These replaced
earlier dataset-centric routes (`GET /tabular/datasets`,
`GET /tabular/datasets/{uid}/schema`) which suffered "first-table-wins" for
multi-table workbooks.

**Open:** the Statistic feature (`read_dataset_frame` /
`read_dataset_preview_frame`) still resolves a multi-table document to table
1 only — needs table-level addressing on the frame-read path (tracked as
INGEST-05).

**Execution guardrails (`features/tabular/execution.py`, issue #2182).** Every
DuckDB call (`query_read`, `search_values`, the preview-frame read) runs as a
single synchronous job on a dedicated `ThreadPoolExecutor`
(`tabular-duckdb`), never on the event loop or the shared default executor —
a connection is created, used, and closed on that one thread; SQL validation
runs inside the job since it opens its own connection.

- **Bounded admission:** `max_concurrent_queries` jobs run at once per
  process, `max_queued_queries` more may wait; beyond that the caller gets
  `503`. The bound is process-wide, not per `TabularService` instance.
- **Bounded wall time:** a job exceeding `query_timeout_seconds` is aborted
  via `connection.interrupt()` **re-issued a few times at short intervals**
  — DuckDB clears its interrupt flag when the next statement starts, so a
  single interrupt landing between a worker's check and its `execute()`
  would otherwise be swallowed and the query would run to completion still
  holding its slot. The budget clock starts at submit, so a job that never
  got a thread is reported as capacity (`503`), not a timeout (`504`).
- **Bounded resources per connection:** every online connection sets
  `threads`, `memory_limit`, and an empty `temp_directory` — the last is not
  optional, since without it DuckDB spills an over-budget operator to disk
  and succeeds, converting a memory problem into an ephemeral-storage one.
- **Over-budget is a caller error:** with spilling off, `OutOfMemoryException`
  is reachable and maps to `400` with an actionable message (its text is
  dropped, not redacted — DuckDB's message names the configured limit and
  advises setting `temp_directory`, neither of which belongs in a response),
  not `500`.
- **Selection is narrowed before mounting:** `validate_read_query` returns
  the authorized aliases the SQL actually references, and only those are
  mounted; `max_selected_datasets` remains a backstop and is the primary
  bound for `search_values`, which has no SQL to narrow with. A workbook cut
  in half by that cap is **omitted** from `searched_dataset_uids` rather
  than listed as searched — listing it would assert a keyword's absence
  from tables that were never opened.
- All three surfaces (`POST /tabular/query`, `POST /tabular/search`,
  `GET .../markdown`) return `503` (no free execution slot) or `504`
  (wall-clock budget exceeded) distinctly from `400` (invalid SQL, no/too-many
  authorized datasets, over memory budget) — overload, a slow query, and a
  caller error stay separable in logs and alerts.

**Known limits, not closed by this guard:** peak process memory is still
unbounded — `memory_limit` governs DuckDB's buffer manager, not
scalar-function allocation, so a relation-free expression like
`SELECT length(repeat('x', 1200000000))` allocates gigabytes faster than any
timeout reacts (P1, needs a subprocess under `RLIMIT_AS` to close). Abort is
best-effort for a worker blocked on `httpfs` socket I/O — `interrupt()`
cannot unblock a stalled read; the bound is `httpfs`'s own retry defaults
(~2 min worst case against a 30s `query_timeout_seconds`), not a deployment
setting, since the remote path can't be exercised offline to tighten it.

### Session-Scoped Attachment Datasets (ATTACH-TAB-01)

CSV files attached directly to a chat conversation (`POST /fast/ingest`) get
a real `tabular_v1` artifact **instead of** the text-chunked vector preview
every other attachment type gets — not alongside it. A truncated Markdown
table (20 rows × 10 cols default) is exactly the kind of imprecise answer
source this feature exists to move away from for CSV, and leaving it in
place would give the agent two competing ways to answer a question about
the same file — a fuzzy, incomplete one (vector search over the preview)
and an exact one (SQL over the full data) — with nothing forcing it toward
the correct one. `fast_ingest` skips building/storing vectors entirely for
`.csv` (`chunks: 0` in the response); the fast-text extraction step still
runs, but only to produce `summary_md` for the frontend's attachment preview
card — that text never reaches the agent's context or the vector index.
Excel/XLSX attachments are not covered by the SQL path yet; they keep both
the text-chunk preview and the "text only" prompt guidance below until a
follow-up increment generalizes this to `tabular_multi_v1`. That follow-up
must also extend `_resolve_owned_attachment_dataset` (or add a
`tabular_multi_v1` sibling) to `TabularService.get_document_markdown` —
untouched in this increment since it is scoped to spreadsheet documents,
which no CSV attachment ever produces, so wiring it in now would be dead
code.

**Ingestion.** `fast_ingest` builds a `DocumentMetadata` for the attachment
directly (`identity.document_uid` = the same uuid used elsewhere for this
attachment, so the one bracketed id the agent is given works for the
tabular/SQL tools; `source.source_tag = "fast_ingest"`, mirroring the
convention non-CSV attachments' vector chunks use; **no tags**) —
deliberately not via `IngestionService.extract_metadata()`/
`process_metadata()`, both built for corpus documents: the former's
versioning step scans the whole metadata catalog for a same-named document
and raises if one exists (wrong semantics for a session-scoped attachment,
and would collide across unrelated users sharing a common filename like
"sales.csv"), and the latter requires `source_tag` to resolve against the
operator-configured `document_sources` registry, which an attachment was
never meant to join. The Parquet conversion itself is fully reused —
`TabularProcessor.process()` (DuckDB CSV→Parquet via the same
`CsvTabularProcessor` delimiter/encoding detection, `tabular_v1` extension),
exactly as corpus CSV ingestion does.

**Why this creates no ReBAC tuple.** `_persist_metadata_and_follow_up` only
writes a ReBAC parent link when `metadata.tags.tag_ids` is non-empty (see
`features/metadata/service.py`). An attachment record carries no tags, so
persisting it through the ordinary path is sufficient by construction — no
bespoke "trusted, tagless" write path was needed. Storage-quota adjustment
and tag-timestamp updates are likewise no-ops for a tagless record; the
`document.created_total` KPI still fires, which is fine.

**Artifact-then-metadata ordering isn't atomic, so a metadata-save failure
compensates rather than orphans (P2, codex review).**
`TabularProcessor.process()` — unchanged, shared with corpus ingestion —
uploads the Parquet object to `content_store` and only updates
`metadata.extensions["tabular_v1"]` in memory before returning; persisting
that metadata is a separate step `_build_attachment_tabular_dataset` does
afterward, and it can fail on its own (a metadata-store outage) after the
artifact already durably exists. Every cleanup path — delete, corpus audit
— is metadata-driven, so an artifact with no row pointing at it can never
be found again on its own. `_build_attachment_tabular_dataset` now deletes
the just-uploaded artifact directly (`_delete_tabular_artifact_objects`,
shared with the normal delete path) before re-raising, rather than leaving
a permanent orphan; a failure in that compensating delete itself is logged
and swallowed so it never masks the original metadata-save error.

**Authorization — no OpenFGA tuple, ever.** Fast-ingested attachments are
deliberately "resource-less" in ReBAC: no tuple, ownership proven via chunk
metadata instead (`_authorize_fast_ingest_delete`,
`ingestion_controller.py:112-127`). `TabularService` stays consistent with
that design rather than reversing it for this one surface. `describe_documents`,
`_select_query_datasets`, and `_get_dataset_or_raise` each already have a
"requested uid not in the ReBAC-authorized set" fallback (used today to
decide `403` vs `404`); every one of them gained one more step, tried first:
a single indexed `metadata_store.get_metadata_by_uid(document_uid)` lookup
(`_resolve_owned_attachment_dataset`, batched as
`_resolve_owned_attachment_datasets` for the two multi-uid call sites),
treated as authorized when `source_tag == "fast_ingest"` and
`identity.uploaded_by == user.uid` (the same equality check
`is_own_session_chunk` already applies to vector chunks). Only if that
doesn't match does the existing ReBAC check decide the `403`.

This is deliberately **not** wired into `_resolve_authorized_datasets`
itself, which enumerates every document the caller can read (used by
`list_documents`/`list_datasets`) — `get_all_metadata()` filters in Python
over every row in the metadata table (`PostgresDocumentMetadataStore.
get_all_metadata`), so folding attachment resolution in there would add an
unbounded table scan to every tabular listing call. The narrower fix costs
one indexed lookup, and only when a document_uid is actually named. Attachment
datasets consequently never appear in a blind `list_documents`/`list_datasets`
enumeration — harmless, since the agent is already handed the uid directly in
the attachment prompt suffix and has no need to "discover" it.

**Exception: `_resolve_authorized_datasets` does exclude attachments in one
specific branch, on purpose (P1, codex review).** When ReBAC is globally
*disabled* — a deployment mode predating ATTACH-TAB-01, where
`lookup_user_resources` returns `RebacDisabledResult` and the method falls
back to listing every metadata row unfiltered — that branch now filters out
`source_tag == "fast_ingest"` records before returning them. Without this,
a ReBAC-disabled deployment would enumerate every user's session-scoped
attachment to every other user through the same blind
`list_documents`/`list_datasets` path the paragraph above says attachments
never appear in — true for the normal, ReBAC-enabled case (no tuple means
`lookup_user_resources` never includes them), false for this one branch,
which bypasses per-user filtering entirely rather than resolving it to
"none." The ownership fallback above is unaffected either way: it never
reads `self.rebac` at all, so an owner's own explicit-uid access keeps
working whether ReBAC is enabled or disabled, and a non-owner's explicit-uid
request still fails the ownership check regardless of what the final
403-vs-404 branch's `has_user_permission` call would answer in that mode
(it only picks the error type, never authorizes access on its own — see
`_select_query_datasets`/`describe_documents`).

**Pointer chunks stay off for attachments, unconditionally.**
`TabularProcessor._emit_pointer_chunk` (§5 below) writes into the *shared*
vector store using `flat_metadata_from(metadata)` — a corpus-oriented
projection with no `scope`/`user_id` fields. A pointer chunk emitted that way
for an attachment would not carry the `scope="session"`/`user_id` markers
every other fast-ingest chunk relies on for isolation, i.e. it could surface
in another user's search. `TabularProcessor.process()` takes an explicit
`emit_pointer_chunk: bool = True` parameter; the attachment path passes
`False` regardless of the deployment's `pointer_chunks_enabled` setting.
Corpus ingestion is unaffected (default unchanged).

**Deletion — re-verifies ownership itself, but honors the same bypass its
caller already got.** `DELETE /fast/delete/{document_uid}` deletes the
Parquet artifact (`content_store`, same prefix corpus re-ingestion pruning
already uses) and the metadata record (`metadata_store.delete_metadata`, a
raw store-level call) alongside the vector cleanup, when a `tabular_v1`
artifact was produced. `_delete_attachment_tabular_dataset` re-checks
`source_tag == "fast_ingest"` and `identity.uploaded_by == user.uid` before
touching anything — the same test `_resolve_owned_attachment_dataset` uses,
not a rubber stamp of the endpoint's upstream authorization. That upstream
check (`_authorize_fast_ingest_delete` → `may_delete_session_document`) was
designed for an idempotent vector-only delete and treats "zero vector
chunks" as safe-to-retry; since a CSV attachment now *always* has zero
chunks by construction (see above), that upstream check alone would let any
authenticated user pass it for any CSV attachment uid, corpus or not —
`_delete_attachment_tabular_dataset`'s own check is what actually stops a
cross-tenant delete, not merely an extra safety net.

`_authorize_fast_ingest_delete` also has its own platform-admin bypass
(`can_manage_platform`, e.g. scheduled conversation erasure authenticating
as a minted service bearer, never as the document's own uploader — CTRLP-12)
— its return value (`is_platform_bypass: bool`) must be threaded into
`_delete_attachment_tabular_dataset`'s own check too, or the two checks
disagree: the endpoint lets the service account in, but the tabular cleanup
then re-derives ownership independently, finds no `uploaded_by` match, and
silently no-ops — HTTP 200, receipt marked `ok`, and the Parquet
artifact/metadata row orphaned with no queue entry left to retry it (P1,
caught in review before merge). `source_tag == "fast_ingest"` stays a hard
requirement regardless of the bypass — this endpoint must never touch a
corpus tabular dataset even for a platform caller.

**Both delete-side checks also require no tags — not just matching
`source_tag` and `uploaded_by` (P1, codex review).** The read-side ownership
check (`_resolve_owned_attachment_dataset`) already required this; the two
delete-side checks didn't, and the gap was wider than a source_tag
collision: the chunk-based fallback in `_authorize_fast_ingest_delete`
(`may_delete_session_document`) doesn't inspect `source_tag` at all, so
*any* tagged document with zero vector chunks — the default for every
CSV/tabular corpus document platform-wide — would have passed this
endpoint's authorization for *any* authenticated user before this fix, tags
notwithstanding. `_authorize_fast_ingest_delete` now refuses a tagged
document outright, before either its tabular-ownership branch or the
chunk-based fallback ever runs; `_delete_attachment_tabular_dataset` gained
the identical check as its own defense-in-depth. Combined with an
operator-configured `document_sources` entry literally named "fast_ingest"
(nothing reserves that string), the narrower version of this gap would
otherwise have let a tagged document's original uploader delete it even
after losing their real ReBAC `DocumentPermission.DELETE` on it (e.g.
removed from the owning team) — a tagged document already has its own
ReBAC-based protection this endpoint doesn't check, and must never be
treated as the resource-less fast-ingest document class however its
`source_tag` happens to read.

**The platform-admin bypass classifies before it bypasses (P1, codex
review).** The check above closed the gap for the non-bypass path, but the
bypass itself still returned `True` on its very first line — before ever
resolving metadata — so a platform-driven delete (scheduled conversation
erasure, CTRLP-12) skipped the tags check and every other classification
entirely. Control-plane never verifies server-side that a session
attachment's `document_uid` (client-supplied at `create_session_attachment`
time) actually names something the calling user fast-ingested, so a forged
or merely mistaken value can name a real, tagged corpus document; the old
bypass would have deleted its vectors outright for the service principal.
`_authorize_fast_ingest_delete` now resolves metadata and evaluates the tags
check and the tabular-ownership branch unconditionally, admin or not — the
bypass (`is_platform_admin`, computed once up front) only ever waives the
*ownership* half of a check, never the *classification* half. For the
metadata-less case (every non-CSV attachment: fast_ingest never writes a
metadata row for them), classification for a service principal can't reuse
`may_delete_session_document` — its per-user match can never be satisfied by
a service account, since the chunks belong to whichever end user actually
uploaded the attachment. `BaseVectorStore.is_session_scoped_document` is the
caller-agnostic sibling: true when the document has no chunks at all (same
retry-safety reasoning as `may_delete_session_document`) or every chunk it
does have carries the `scope="session"` marker, false — refusing the bypass
— the moment one chunk lacks it (a real corpus document, chunks included).

**A vector-store lookup failure must not read as "no chunks, therefore
safe."** `is_session_scoped_document`/`may_delete_session_document` both
treat an empty `get_chunks_for_document` result as "genuinely nothing there"
(the retry-safety case). Every concrete vector store's `get_chunks_for_document`
used to catch its own client's exceptions and return `[]` — meaning a real
backend outage during a classification call was indistinguishable from "the
vectors are already gone," and the platform-admin bypass would be granted on
a document nobody actually classified. All five backends (OpenSearch,
PGVector, ChromaDB, ClickHouse, in-memory) now raise instead of swallowing
on a genuine fetch failure — only `NotImplementedError` (the backend never
supports the capability) still resolves to a plain `False`/`""`. The
exception then propagates out of `_authorize_fast_ingest_delete` uncaught
into the app's generic exception handler (`fred_core.common.register_exception_handlers`),
producing a 500 rather than a false authorization.

**Vector deletion must be truthful too, the same way tabular cleanup now
is.** `_delete_fast_vectors` calls `delete_vectors_for_document`; OpenSearch
and ClickHouse already raised `RuntimeError` on failure, but PGVector and the
in-memory store caught the exception and returned normally — silently
leaving the vectors in place while `_delete_fast_ingest_artifacts` (and the
route) reported success, the same false-erasure shape the tabular-cleanup
fix above closes. Both now raise like their siblings.

Reusing `MetadataService.delete_document_and_artifacts_trusted` here was
considered and rejected: it also runs storage-quota release
(`_delete_and_release`),
which requires a live Postgres engine even to determine there is nothing to
release for a tagless, quota-exempt attachment — infrastructure this narrow
cleanup has no other reason to depend on.

**Tabular cleanup failure must not report a successful erasure (P1, codex
review).** `_delete_attachment_tabular_dataset` used to catch every
exception from the actual delete work and log-and-return, so a Parquet or
metadata-store failure left the dataset behind while the route still
returned HTTP 200 — control-plane's `ConversationErasureService.erase_session`
would then record the attachment store `ok=True`, delete its own attachment
row, and (for a full session erasure) go on to delete the session metadata
row too, with nothing left pointing at the orphaned dataset to make it
retryable. The classification early-returns ("nothing to clean up") stay
silent — those are not failures — but the actual artifact/metadata delete
now raises on error like every sibling cleanup step in this file. No
control-plane change was needed for this: `_delete_knowledge_flow_attachment`
already turns any non-2xx into `SessionAttachmentRequestError`, and
`erase_session` already isolates each store's failure, retains its record,
and skips deleting the session metadata row until every store reports
`ok=True` (RFC §2.1 retry-safety) — this Knowledge Flow fix is what makes
that existing control-plane machinery actually see the failure instead of a
false 200.

**Known open gap — the attachment-ownership predicate is hand-rolled three
times.** `_authorize_fast_ingest_delete`'s tabular-ownership branch,
`_delete_attachment_tabular_dataset`'s re-check, and
`TabularService._as_owned_attachment_dataset` each independently test
`source_tag == "fast_ingest"` + no tags + `uploaded_by` + artifact-present;
`is_session_scoped_document` is also a near-duplicate of
`may_delete_session_document` (chunk-scope check, minus the `user_id`
match). A code-review pass on the classify-before-bypass fix flagged both as
real drift risk (a future change to either predicate must be applied
everywhere it's copied or silently diverges — as already happened once, per
the tags-check history above) but judged consolidating either one too broad
a change to bundle into a security fix. Deliberately left as-is here;
revisit as a standalone simplification pass.

**Prompt suffix.** `build_attachment_context_suffix`
(`libs/fred-runtime/fred_runtime/react/react_prompting.py`) tells agents
`.csv` attachments are SQL-queryable *only* — not indexed for search at all,
so the conversation search tool must never be called for one (it would find
nothing, since no vector chunk exists). `.xlsx`/`.xls`/`.xlsm` keep the
original "text only, not SQL-queryable" wording, unaffected, until Excel
gets the same treatment as CSV.

The suffix only promises SQL-queryability when the calling agent instance
actually has the tabular MCP server bound: `general_assistant` (#2429) ships
with zero default capabilities, so a CSV attachment can carry a real
`tabular_v1` dataset while the agent that sees it has no `read_query`/
`search_tabular_values` tool to call. `compose_system_prompt` now takes a
required `tabular_tools_available` flag, computed by each runtime
(`react_runtime.py`, `deep_runtime.py`) via
`react_tool_binding.tabular_tools_bound(bound_tools)` — checking
`BoundTool.mcp_server_id == MCP_SERVER_KNOWLEDGE_FLOW_TABULAR` against the
tools actually resolved for this run, the same bound-tool list the tool
listing suffix and Deep's filesystem-availability notice
(`_allows_standard_filesystem_tools`) already derive their own
availability signals from. When the server isn't bound, both the per-line
CSV annotation and the paragraph's CSV sentence switch to telling the model
the dataset cannot be queried at all in this session, instead of pointing it
at tools it doesn't have.

**Known open gap.** The agent isn't guaranteed to call schema-discovery
(`get_tabular_documents_schemas`) before its first `read_query` on an
attachment — live-testing hit exactly this (a guessed SQL alias, `400`,
self-corrected retry). `list_tabular_documents` can't help here since it
deliberately never enumerates attachment datasets (see above). Tracked as
open in `TABULAR-DATA-AGENTIC-ANALYSIS-RFC.md`, alongside a related,
not-yet-designed pattern for per-row agentic analysis over a resolved row
set — not solved here since neither has a decided direction yet.

**Known open gap — no storage quota.** `POST /fast/ingest` performs no
quota check for any attachment type; the tabular path specifically
converts the entire uploaded CSV to Parquet with no size cap, unlike the
text/vector path's bounded `FastTextOptions.max_chars`. `_evaluate_quota`
(issue #2150) could gate it, but `MetadataService._resolve_storage_deltas`
deliberately excludes every untagged document from accounting — a
rationale ("no route can ever release the charge") that doesn't actually
hold for this document class, which has a real delete path
(`DELETE /fast/delete/{document_uid}`). Tracked in issue #2543, scoped to
every fast-ingest attachment type, not CSV-specific — deliberately not
fixed in this increment (resource accounting is its own unit of work).

## 3. Tabular Reads on GCS — Signed URLs

Backend-internal tabular reads (DuckDB mounting Parquet, §2) need a
DuckDB-readable location. On GCS this is a short-lived **V4 signed URL**
minted via IAM `signBlob` under Workload Identity — never a service-account
JSON key:

- `GcsContentStore.get_presigned_url_internal(...)` implements it, gated by
  config `content_storage.signing_service_account_email` (required when
  `content_storage.type: gcs`; startup fails clearly if missing rather than
  guessing).
- IAM: the signing service account needs `storage.objects.get` on the
  tabular-artifacts bucket; the Workload Identity service account needs
  `iam.serviceAccounts.signBlob` on the signing account
  (`roles/iam.serviceAccountTokenCreator`).
- TTL bounded by `storage.tabular_store.query.internal_presigned_ttl_seconds`.
  Signed URLs are never returned in API responses, MCP payloads, or logs —
  including on error: object URLs are redacted from caught `duckdb`/`httpfs`
  exceptions before logging (a failed Parquet read otherwise echoes the full
  signed URL in the exception string).
- Cross-backend invariant: MinIO/S3-compatible stores keep serving tabular
  reads through their existing backend-internal presigned-URL path; local
  storage keeps the direct filesystem fallback. The GCS path is additive and
  does not change either.
- Browser-facing document/VFS sharing is unrelated and unchanged — it uses
  application-level HMAC download tokens, not provider signed URLs;
  `GcsContentStore.get_presigned_url` (the browser-facing method) still
  raises `NotImplementedError` for knowledge-flow documents.
- **Amendment — control-plane team assets (banner/logo):** the
  control-plane's `TeamService` serves these straight to the browser with no
  HMAC-token fallback of its own, so `fred_core.store.GcsContentStore`'s
  public `get_presigned_url(...)` — the browser-facing method — also gained
  real V4 signed URLs (same IAM `signBlob` mechanism, independent signing
  service account, 1-hour TTL set by the caller). Scoped to `fred-core`'s
  generic object store backing control-plane team assets only; knowledge-flow
  document sharing is untouched by this amendment.

## 4. Targeted Similarity / Comparison Search (KF-SIMILARITY-SEARCH)

A search mode for **comparison** agents (e.g. the rags assessment agent),
additive alongside conversational Q&A search: *given an anchor passage,
return the passages most similar to it within a set of targets named on the
call*, ranked best-first. The key difference from conversational search is
**where targeting lives** — conversational search takes its scope from the
request/conversation (chosen once); this mode takes its target from the call
(re-aimable per query), which is what document-to-document comparison needs.

- **`POST /vector/similarity-search`** (`SimilaritySearchRequest`): `anchor`
  (required text), `document_uids` + `document_library_tags_ids` (targets —
  **at least one target is required**, a `model_validator` rejects
  empty-target calls as a client error, since targeting precision is the
  point), `top_k` (1–100), `rerank` (default **on**), optional `min_score`.
- **MCP** — auto-exposed by the Text MCP server via
  `include_tags=["Vector Search"]`; agents see `similarity_search` with no
  extra wiring.
- **Capability** - `document_similarity`, the first-order path, sitting on the
  typed `RuntimeServices.document_similarity` port and offering the agent one
  tool, `find_similar_passages`. Targeting is narrowed to `document_uids`
  here: folder targets stay MCP-only until an agent needs them. The uids come
  from the model per call, so the adapter bounds them by the session binding
  and refuses to widen when that intersection is empty. A weak hit stays
  citable, unlike under corpus search - the caller named the targets, so there
  is no corpus-wide noise to filter out - though dataset-pointer chunks never
  are. See `RUNTIME-EXECUTION-CONTRACT.md` §8.59.
- Implementation is a thin orchestration over existing primitives, no new
  search machinery: targeted `search(...)` (ReBAC-filtered candidate pool) →
  `rerank_documents(...)` (cross-encoder, best-first) → `top_k` → optional
  `min_score` cutoff.
- Same corpus, same auth model as conversational search — no new ingestion,
  embedding, or storage. "Compare document A to document B" becomes: for
  each passage of A, call this with `anchor = passage`, `targets = [B]`,
  `top_k = 1`.
- Deferred: passage-level targeting (target is document/folder only for
  now), a "best per target document" ranking knob.

## 5. Dataset-Pointer Chunks for RAG Discovery (RUNTIME-10)

Tabular data is structurally invisible to the vector index — `TabularProcessor`
never touches an embedder, so a generalist agent doing conversational search
never learns a relevant dataset exists and silently concludes "no information
found." Increment 1 (shipped, gated off by default via
`storage.tabular_store.pointer_chunks_enabled`) adds exactly **one pointer
chunk per dataset** to the vector index, cheaply bounding top-k pollution:

- **Deterministic id** — `chunk_uid = f"{document_uid}::pointer"` — gives
  real upsert-by-id semantics (OpenSearch bulk `_id` derived from
  `chunk_uid`), so reprocessing a dataset overwrites rather than duplicates
  its pointer.
- **Injection-resistant fixed template** — only title and column
  name/type spans are dataset-derived; the surrounding delimiters and the
  instruction note ("this is a structured dataset — inspect it with
  `list_tabular_datasets`/`get_tabular_dataset_schema`, then query with
  `read_query`... do not guess at values not shown above") are constant,
  authored text, never interpolated from untrusted dataset content. This is
  a mitigation, not a closure, of prompt-injection risk via untrusted
  retrieved content — a pre-existing, generic surface, not a new category.
- **No sample values in increment 1** — title, column names, and types are
  enough to make a pointer chunk semantically matchable; sample values carry
  materially higher exposure with no PII/column-classification mechanism to
  gate them. Adding them back needs a human-decided, default-deny
  safe-pattern allowlist first (categorical/enum-like column names only),
  not a denylist.
- **`chunk_kind: content | dataset_pointer`** — minimal two-value enum
  (default `"content"` for chunks written before this shipped), added via
  the existing additive-mapping-update path
  (`SAFE_METADATA_MAPPING_UPDATES`) — no reindex, no recreation. Generalizing
  to a `source_kind` enum for future modalities is deferred until a second
  non-prose modality actually exists in code.
- **Lifecycle** reuses `delete_vectors_for_document` unchanged — the pointer
  shares its dataset's `document_uid`, so delete/reingest already cleans it
  up with no new code.
- **`sources` exclusion** — `VectorSearchHit.chunk_kind` lets both
  search-tool front-ends exclude `dataset_pointer` hits from the citation
  list while still passing them to the model's tool content, so the
  discovery mechanism works without polluting citations. The same pass added
  `select_citable_sources`, excluding real-content hits scoring below a
  `min_score_ratio` (default 0.5) of the best hit in the same search call —
  a general RAG quality fix, not pointer-specific.
- **ACL staleness** — pointer chunks inherit the same pre-existing,
  platform-wide characteristic as every indexed chunk: vector search's
  authorization is enforced via a term filter on tag/document-uid fields
  baked in at index time, so it is only as fresh as the chunk's last
  reindex, unlike the tabular path's live per-request ReBAC check. Not a new
  risk category, not fixed by this work.

## 🧼 Summary

| Step             | Push File                         | Pull File                            |
| ---------------- | --------------------------------- | ------------------------------------ |
| Discovery        | Uploaded by user                  | Scanned from external source         |
| Initial metadata | Created and saved immediately     | Not created yet                      |
| Ingestion input  | `FileToProcess(document_uid=...)` | `FileToProcess(external_path=...)`   |
| Metadata usage   | Retrieved from store              | Created via `to_virtual_metadata()`  |
| Storage          | File and metadata saved           | Virtual metadata created, then saved |

This unified design supports both push and pull documents without duplication, and is compatible with both Temporal workflows and simpler ingestion flows.
