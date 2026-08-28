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
