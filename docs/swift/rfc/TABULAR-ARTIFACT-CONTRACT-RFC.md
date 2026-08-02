# RFC: Tabular Artifact & DuckDB SQL-Mounting Contract

**ID:** INGEST-06
**Status:** implemented (as-built) — this RFC documents an architecture already shipped on branch `swift`; it introduces no new work, it gives the existing contract a home.
**Author:** Timothé Le Chatelier
**Date:** 2026-07-08
**Scope:** `apps/knowledge-flow-backend` — the metadata contract, object-store layout, SQL alias scheme and DuckDB mounting that turn ingested tabular data into an agent-queryable SQL surface.
**Producers:** [EXCEL-EXTRACTION-PIPELINE-RFC.md](EXCEL-EXTRACTION-PIPELINE-RFC.md) (INGEST-02 — spreadsheet, multi-table) · the CSV tabular path (single-table, predates this RFC).
**Consumers:** the document-centric tabular MCP (INGEST-04, EXCEL-EXTRACTION §10) · the Statistic feature (INGEST-05).
**Related:** [GCS-TABULAR-SIGNED-URL-RFC.md](GCS-TABULAR-SIGNED-URL-RFC.md) (FILES-06 — the read path) · [OBJECT-STORAGE-NAMING-RFC.md](OBJECT-STORAGE-NAMING-RFC.md) (OPS-05 — key naming).
**Contract impact:** internal knowledge-flow contract, stored in `DocumentMetadata.extensions`. It is **not** one of the frozen platform contracts (`RUNTIME-EXECUTION-CONTRACT`, `CONTROL-PLANE-PRODUCT-CONTRACT`); it is versioned in-band by its `_v1` extension keys.

---

## 1. Why this RFC exists

Fred can answer analytical questions ("sum column C where B = X", "how many rows
per region") by mounting ingested tables in DuckDB and letting an agent run
read-only SQL. Two ingestion producers feed that surface:

- the **CSV path** — one document → one table (`tabular_v1`), and
- the **spreadsheet path** (INGEST-02) — one Excel workbook → N tables
  (`tabular_multi_v1`).

Both share one spine: a typed metadata artifact, a canonical object-store layout,
a deterministic SQL alias scheme, and a per-query DuckDB mounting model. That
spine was implemented and is load-bearing for three separate features, yet it was
never written down — it lived only inside code and was referenced piecemeal
(EXCEL-EXTRACTION §10/§11, GCS-TABULAR for the read path). This RFC records it so
producers and consumers converge on one contract instead of re-deriving it.

Nothing here is new work; it is the as-built contract.

---

## 2. The metadata contract (`DocumentMetadata.extensions`)

A document that carries queryable tables stores a typed payload under one of two
extension keys. Authorization stays **document-level** (ReBAC on the document);
SQL exposure is **table-level**.

### 2.1 `tabular_v1` — single-table document (CSV)

`TabularArtifactV1` (`features/tabular/artifacts.py`):

| Field | Type | Meaning |
| --- | --- | --- |
| `dataset_uid` | str | The document uid (one dataset per document). |
| `object_key` | str | Canonical Parquet key (§3). |
| `source_revision` | str | Document `sha256` — makes the key content-addressed. |
| `format` | str | `"parquet"`. |
| `row_count` | int | Rows in the table. |
| `columns` | `list[TabularColumnSchema]` | Ordered `{name, dtype}` schema (§4). |
| `generated_at` | str | ISO-8601 UTC. |
| `file_size_bytes` | int | Stored artifact size. |

### 2.2 `tabular_multi_v1` — multi-table document (spreadsheet)

`TabularMultiArtifactV1` holds `tables: list[TabularTableArtifactV1]`.
`TabularTableArtifactV1` **extends** `TabularArtifactV1` (so each table mounts
exactly like a single-table dataset) and adds:

| Field | Type | Meaning |
| --- | --- | --- |
| `query_alias` | str | The exact SQL relation name exposed to agents (§5). **Stored**, because it must match the alias printed in the workbook's `output.md` catalog. |
| `sheet` | str | Source sheet name. |
| `table_id` | str | Extractor id `<sheet>.tN`. |
| `title` | str? | Table title extracted from the sheet (RFC INGEST-02 A4). |
| `range` / `data_range` | str? | A1 footprint and kept-body range. |

`read_tabular_artifact` / `read_tabular_multi_artifact` rehydrate the typed view;
`write_*` persist it (`model_dump(mode="json")`). A malformed payload logs a
warning and reads as absent rather than crashing a list/query — except at the
output stage, where a malformed sidecar is a hard error (see EXCEL-EXTRACTION
§11.4).

**Why two keys, not one generalized key.** `tabular_v1` predates the spreadsheet
work and is consumed by the CSV path unchanged; generalizing CSV to a one-element
`tabular_multi_v1` was rejected to avoid a data migration of already-ingested
documents. The resolver (§6) reads both.

---

## 3. Object-store layout

All artifacts live under the configured `storage.tabular_store.artifacts_prefix`
(default `tabular/datasets`):

```
<artifacts_prefix>/<document_uid>/<source_revision>/data.parquet        # tabular_v1  (CSV)
<artifacts_prefix>/<document_uid>/<source_revision>/<Sheet.tN>.parquet   # tabular_multi_v1 (one per table)
```

- `source_revision` is the document `sha256` (`compute_source_revision`), so a
  re-ingested revision writes to a fresh path and the old one can be pruned.
- Every table of a workbook shares the **per-document** prefix
  `<artifacts_prefix>/<document_uid>/` (`document_artifact_prefix`), so revision
  cleanup is one `list_objects` + prune, identical for CSV and spreadsheet.
- Helpers: `build_tabular_object_key` (single), `build_tabular_table_object_key`
  (per table), `document_artifact_prefix` (cleanup).

---

## 4. Schema vocabulary

`DTypes = Literal["string","integer","float","boolean","datetime","unknown"]` —
one stable, UI/LLM-friendly vocabulary independent of pandas or DuckDB internals.

- `dataframe_dtype_to_literal` / `dataframe_schema` derive it from a pandas
  DataFrame (spreadsheet input stage, which materializes DataFrames).
- `duckdb_dtype_to_literal` / `duckdb_schema` derive it from DuckDB column
  metadata (the scalable CSV-to-Parquet path, which never materializes a
  DataFrame).

Both produce the same `TabularColumnSchema{name, dtype}` list, so a downstream
consumer cannot tell which producer wrote a table.

---

## 5. SQL alias scheme (determinism is the contract)

The relation name an agent types in SQL must equal the name the runtime mounts
**and** the name the producer advertised (a workbook's `output.md`, or a dataset
listing). Any drift makes valid agent SQL fail `validate_read_query`. One shared
helper family guarantees it:

| Producer | Helper | Shape | Example |
| --- | --- | --- | --- |
| CSV (single) | `build_default_query_alias(uid, name)` | `d_<uid12>_<stem>` | `d_12345678_123_sales_export` |
| Spreadsheet (table) | `build_table_query_alias(uid, sheet, index)` | `d_<uid12>_<sheet>_t<N>` | `d_12345678_123_ventes_2026_t1` |

- `<uid12>` = the sanitized 12-char document prefix; `sanitize_sql_name` makes
  every token a safe DuckDB identifier.
- The per-sheet table **index** is part of the name because a sheet can hold
  several tables (`build_table_query_alias` would otherwise collide).
- The spreadsheet input stage stamps `query_alias` into `tabular_multi_v1` and
  prints the same value in `output.md`; the resolver re-derives nothing, it reads
  the stored alias.
- `_claim_alias` (resolver) only guards the theoretical cross-document collision
  when two documents are mounted in one query: it renames and **logs a warning**,
  because the served alias then diverges from the stored catalog. This is the one
  sanctioned divergence, and it is observable.

---

## 6. Resolution & DuckDB mounting

`TabularService` (`features/tabular/service.py`) turns authorized documents into
mounted relations:

1. **Resolve** (`_resolve_authorized_datasets`): for each ReBAC-authorized
   document, read `tabular_v1` → one `ResolvedDataset`, or `tabular_multi_v1` →
   **one `ResolvedDataset` per table**. Authorization is checked once at document
   level; expansion to tables happens after.
2. **Select** (`_select_query_datasets`): a `/tabular/query` request naming a
   workbook uid mounts **all** of that workbook's tables (this is why a single
   document uid gives an agent every table).
3. **Mount** (`query_read` → `_mount_datasets`): a **fresh in-memory DuckDB
   connection per query** mounts only the caller's readable datasets as read-only
   views over Parquet. No cross-query state, no writable tables.
4. **Locate** (`_resolve_dataset_location`): remote object stores resolve the
   Parquet through a short-lived **backend-internal presigned URL**
   (`get_presigned_url_internal`, TTL `query.internal_presigned_ttl_seconds`),
   read via DuckDB `httpfs`; the local filesystem store uses a direct path. A
   store offering neither fails as an explicit unsupported operation. (Read-path
   details and the GCS signing requirement: GCS-TABULAR-SIGNED-URL-RFC.)
5. **Redact** (`_redact_signed_urls`): signed URLs are stripped from any caught
   `duckdb`/`httpfs` error before it is logged or surfaced — they never reach
   logs, API responses, or MCP payloads.

The runtime is **read-only DuckDB over Parquet**. It is not a SQLAlchemy layer
over PostgreSQL/MySQL/SQLite (the pre-INGEST-04 `mcp-tabular` description wrongly
claimed that; EXCEL-EXTRACTION §10 corrected it).

### 6.6 Execution guardrails (amended 2026-07-31, issue #2182)

Steps 1–5 above describe *what* is mounted. This subsection describes *how much*
of it may run, and is load-bearing for go-live: before it, every DuckDB call ran
synchronously on the FastAPI event loop, unbounded, on routes that are also MCP
tools — so one caller could stall the pod for every other request.

`features/tabular/execution.py` owns the guard. Four rules define the contract:

1. **One operation, one worker thread.** `query_read`, `search_values` and the
   preview frame read each run as a single synchronous job on a dedicated
   `ThreadPoolExecutor` (`tabular-duckdb`), never on the event loop and never on
   the shared default executor. A connection is created, used and closed on that
   one thread. SQL validation runs inside the job because it opens its own
   DuckDB connection.
2. **Bounded admission.** `max_concurrent_queries` jobs run at once per process,
   with `max_queued_queries` more allowed to wait; beyond that the caller gets
   `503`. The bound is process-wide, not per `TabularService` instance — the
   tabular controller and `ContentService` each build their own instance.
3. **Bounded wall time.** A job exceeding `query_timeout_seconds` is aborted.
   Abort is `connection.interrupt()` plus an explicit flag checked before each
   mount, because `interrupt()` only affects a statement that is currently
   executing — and, since DuckDB clears its interrupt flag when the next
   statement starts, the abort is **re-issued a few times at short intervals**
   so one landing between a worker's check and its `execute()` is not swallowed.
   Without that retry a timed-out query runs to completion still holding its
   slot. The slot is released when the worker thread actually returns, never
   before. The budget clock starts at submit, so a job that never got a thread
   is reported as capacity (`503`), not as a timeout (`504`).
4. **Bounded resources per connection.** Every *online* connection sets
   `threads`, `memory_limit`, and an empty `temp_directory`. The last is not
   optional: without it DuckDB spills an over-budget operator to disk and
   completes, so `memory_limit` bounds nothing and merely converts a memory
   problem into an ephemeral-storage one. The throwaway connection
   `_parse_read_statement` opens for `json_serialize_sql` (`utils.py`) sets
   `threads=1` only: it never executes a plan, so it needs no memory budget, but
   left unset it would spin up a thread pool sized from the host's CPU count
   rather than the container's limit.
5. **Over-budget is a caller error.** Because spilling is off,
   `duckdb.OutOfMemoryException` is now reachable and maps to `400` with an
   actionable message, not to `500`. Its text is dropped rather than redacted:
   DuckDB names the configured limit and advises setting `temp_directory`,
   neither of which belongs in an API response.

**Selection is narrowed before mounting.** `validate_read_query` returns the
authorized aliases the SQL actually references, and only those are mounted; a
query referencing none is rejected with `400`. `max_selected_datasets` remains
as a backstop for queries and is the primary bound for `search_values`, which
has no SQL to narrow with and flags truncation through the existing
`tables_truncated` field.

One deviation from issue #2182, which asked to leave `searched_dataset_uids`
alone: a workbook expands to one dataset per table, so the cap can slice through
the middle of a document. A document that was cut is now **omitted** from
`searched_dataset_uids`, because listing it would tell an agent "the value is
not in this document" when tables of it were never opened — a wrong answer
rather than a partial one. Documents skipped by the `max_matching_tables` break
keep the original semantics.

**Known limit — this guard does not bound peak process memory.** `memory_limit`
governs DuckDB's buffer manager, not scalar-function allocation. A query such as
`SELECT length(repeat('x', 1200000000))` allocates gigabytes, is not slowed by
any timeout, and passes every check above. See §9.4.

---

## 7. Document kinds & the API surface

`TabularDocumentKind = Literal["csv","spreadsheet"]` classifies a document by its
artifact key (`_document_kind`). The document-centric API (INGEST-04) is built on
this contract:

- `GET /tabular/documents` → `TabularDocumentResponse` (one per document; `kind`,
  nested `TabularTableSummary[]`, tags — no columns, kept light for LLM context).
- `GET /tabular/documents/schemas?document_uids=…` →
  `TabularDocumentSchemaResponse` (batch; **all** tables of each document with
  full `columns[]`).
- `GET /tabular/documents/{uid}/markdown` → `TabularDocumentMarkdownResponse` (a
  spreadsheet's `output.md`; 404 when no `tabular_multi_v1`).
- `POST /tabular/query` → read-only SQL over the mounted relations.
- `POST /tabular/search` → keyword value-locator over the mounted relations.

Both `POST` routes — **and `GET /markdown/{document_uid}`**, whose CSV preview
renders from the same Parquet artifact and shares the same execution budget —
return `503` when the process has no free DuckDB execution slot and `504` when a
job exceeds its wall-clock budget (§6.6). These are deliberately distinct from
`400`, which now covers three caller faults: invalid SQL, a query referencing no
authorized dataset or too many of them, and a query over its memory budget. So
overload, a slow query and a caller error stay separable in logs and alerts.
None of this appears in the OpenAPI spec: the routes declare no `responses`
block, so the generated frontend client is unaffected.

Route behaviour, replacement of the dataset-centric routes, and the OpenAPI
contract impact are owned by **EXCEL-EXTRACTION §10**; this RFC owns the
underlying artifact/alias/mounting model those routes expose.

---

## 8. Authorization model

- **Document-level ReBAC** decides *whether* a caller sees a document at all
  (list, schema, markdown, and query selection all filter by it).
- **Table-level SQL exposure** is a projection of that decision: once a document
  is authorized, every one of its tables is mountable. There is no per-table
  authorization — a workbook is one authorization unit.
- Backend-internal signed URLs are never exposed (§6.5).

---

## 9. Open items

| # | Item | Status |
| --- | --- | --- |
| 9.1 | **Statistic first-table-wins** — `read_dataset_frame` / `read_dataset_preview_frame` resolve a multi-table document to table 1 only; the Statistic MCP analyses just the first table of a workbook. Needs table-level addressing (alias or index) on the frame-read path. | open — tracked as **INGEST-05** |
| 9.2 | **Cross-document alias collision** — `_claim_alias` renames on collision and logs; the served alias then diverges from the stored `output.md` catalog. Acceptable and observable; revisit only if it occurs in practice. | accepted |
| 9.3 | **Contract versioning** — a `tabular_v2` / `tabular_multi_v2` would need a metadata migration or a dual-read window. No trigger yet. | deferred |
| 9.4 | **Peak process memory is unbounded** — `memory_limit` governs DuckDB's buffer manager only. `SELECT length(repeat('x', 1200000000))` references no relation, passes read-only validation, mounts nothing, and allocates gigabytes faster than any timeout can react (measured: 796 MB RSS at a third of that size, with `memory_limit='256MB'`, `threads=1`, spilling disabled). Rejecting relation-free queries closes that exact shape but not the same expression with a `FROM` clause. A real bound needs the DuckDB job in a subprocess under `RLIMIT_AS`. | **open — P1**, follow-up to #2182 |
| 9.5 | **Abort is best-effort for network I/O** — `interrupt()` aborts DuckDB execution in milliseconds but cannot unblock a socket read inside `httpfs` (measured: a worker blocked on a stalled read stayed blocked 5 s after `interrupt()`, until the read returned). A stalled object store therefore holds execution slots until the socket resolves, degrading tabular to `503`/`504` rather than wedging it, since slots are released when the thread returns. The bound is `httpfs`'s own defaults, measured with the extension loaded on 1.5.4: `http_timeout=30`, `http_retries=3`, `http_retry_backoff=4`, `http_retry_wait_ms=100` — so worst case is roughly 2 min per HTTP request, against a 30 s `query_timeout_seconds`. Not indefinite, but ~4× the configured budget and set by DuckDB rather than by deployment. All four are settable per connection alongside `threads`/`memory_limit`, which would tighten it; not done here because the remote path cannot be exercised offline. | open — follow-up to #2182 |
| 9.6 | **Disabling spill turns some previously-succeeding queries into errors** — an over-budget sort or aggregate used to write to disk and return `200`; it now raises `OutOfMemoryException`, mapped to `400` with an actionable message (§6.6). This is the intended trade (a bounded failure beats an unbounded disk write) but it is a user-visible behaviour change for large queries that previously worked. | accepted |

---

## 10. Decision recorded

This RFC ratifies, after the fact, the contract that shipped under INGEST-02
(producer) and INGEST-04 (consumer surface):

1. Two typed metadata extensions — `tabular_v1` (single) and `tabular_multi_v1`
   (multi) — with `TabularTableArtifactV1` extending the single-table base.
2. Content-addressed object-store layout under `artifacts_prefix/<uid>/<rev>/`,
   shared by both producers for uniform cleanup.
3. Deterministic, stored SQL aliases; the producer's catalog, the metadata, and
   the mounted relation name are the same string by construction.
4. Read-only, per-query DuckDB mounting over Parquet, document-level ReBAC with
   table-level SQL projection, signed-URL redaction on errors.

No GitHub execution issue is opened: the code already shipped under INGEST-02/04.
This is documentation-convergence, per the project close-out rules.
