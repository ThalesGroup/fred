## Context

See [proposal.md](proposal.md) for the motivation. `describe_documents` currently authorizes requested documents, reads each spreadsheet's `output.md`, then copies stored `artifact.columns` into the response. CSV and Excel ingestion classify strings, store categorical samples and calculate numeric bounds. A current service test explicitly expects descriptions of old metadata to leave bounds null without reading Parquet. The response model already has optional `sample_values`, `min_value` and `max_value`, so its wire shape can stay stable.

## Goals / Non-Goals

**Goals:**

- Read category samples and numeric bounds of only the documents being described, after document and library scope checks.
- Replace any stored samples or bounds in the response with values from the queryable Parquet artifacts on every call.
- Keep each batch within the existing tabular worker, timeout, capacity and memory budgets.

**Non-Goals:**

- Reclassify string columns at description time, alter SQL query behavior, or migrate historical document metadata.
- Add numeric columns to the lightweight `list_tabular_documents` response.

## Decisions

### Read column values in the description service

Build the response columns from stored names, types, `is_categorical` and `has_two_values`, then clear old samples and bounds. For `is_categorical=true`, overlay distinct non-null string values from Parquet; for numeric columns, overlay finite bounds. Classification remains an ingestion-time decision, so non-categorical and unclassified strings have no samples. Do not update the artifact or metadata store. The alternative, backfilling metadata or reading values only when absent, would keep values tied to ingestion or allow stale responses.

### Read through one guarded DuckDB job per description batch

After authorization, reject a batch above `max_selected_datasets` before scanning any table. Then check catalog availability and read the requested tables inside one `run_duckdb_job` call. Open one bounded connection, resolve each Parquet location through the existing content-store path, initialize `httpfs` only if needed, check the abort handle between tables, and close the connection on every outcome. For each table, query all numeric columns together with quoted identifiers and finite-value filters; query all distinct values for columns marked categorical, even if the current table has more values than at classification. Validate readability with a count query for tables with neither numeric nor categorical columns. Return values in column order. Wrap Parquet reads with the existing signed-URL redaction helper. One job gives the whole batch one capacity slot and wall-clock budget; unguarded per-table threads would bypass those limits.

### Store only classification and type during ingestion

Excel's sidecar and CSV's artifact retain schema and categorical verdicts, but no category samples or numeric bounds. Keep the current bounded distinct-value inspection in each producer to decide `is_categorical` and `has_two_values`, then discard its values rather than persisting them. Remove numeric aggregation from both producers. The optional response fields remain for backward-compatible reads of old metadata.

## Risks / Trade-offs

- [Description latency and remote reads grow with the number and size of tables] → Aggregate all numeric columns of a table in one statement, read categorical values only for classified columns, and measure a representative multi-table workbook under the existing timeout.
- [A large workbook or newly high-cardinality categorical column may exceed the current time or memory budget] → Reject batches above the dataset scan limit and return the existing capacity/timeout/error response for resource exhaustion; do not silently omit values. Keep the whole request in one guarded job.
- [Stored samples and bounds on old documents can disagree with current data] → Always overwrite them in response only; regression tests cover both absent and stale stored values.
- [Remote Parquet errors may contain signed URLs] → Reuse the dataset read redaction boundary and test that failure responses do not expose locations.

## Migration Plan

No metadata migration or re-ingestion is needed. Deploy the service and ingestion changes together; existing sample and bound fields remain readable but do not determine descriptions. Rollback restores the previous stored-value behavior, including null bounds for old documents.
