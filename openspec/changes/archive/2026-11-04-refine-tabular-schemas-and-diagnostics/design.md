## Context

See `proposal.md` and the two delta specs. `describe_documents` currently resolves all authorized tables, checks the selected-table budget, then scans category values and numeric bounds for every table of each requested document. Stored artifact columns and response columns share `TabularColumnSchema`. The API, packaged prompt, SQL-agent prompt, generated frontend types and trace parser/rendering use the old category fields.

The Excel extractor's `b4_clean_and_coerce` recognizes native and text dates but rebuilds those columns with `dtype=object`. `_write_extracts` converts object columns to pandas strings before Parquet export. A local three-value reproduction produced VARCHAR today and TIMESTAMP_NS when preserving `datetime64[ns]`. The API already maps native temporal types to `datetime`.

`query_read` validates authorized relation references and mounts only referenced datasets. Diagnostics must use that same mounted subset, not the wider workbook, selected-document inventory or description catalog.

## Goals / Non-Goals

**Goals:** reduce schema payload and unnecessary description scans, preserve actual temporal data, and provide useful column diagnostics without expanding SQL scope.

**Non-Goals:** change UIDs or SQL aliases, auto-correct SQL, inspect unreferenced tables, add global date guesses or convert historical artifacts on read. Proposal 4A/4B changes only the packaged system prompt. Proposal 5 is rejected; existing legacy-date behavior/guidance is retained without additions. The developer authorizes reingesting the one synthetic campaign workbook, not a general historical migration.

## Decisions

### 1. Select existing tables without renaming them

Add optional `table_names: list[str]` to the description route/tool and service. Omitted or empty means all tables. An entry matches an exact existing `query_alias`, or an exact sheet/title label resolving to one table across the requested documents. Reject unknown or ambiguous selectors before table-data reads; use existing aliases to disambiguate. Do not fuzzy-match names or substitute these human labels into SQL. Deduplicate selections and retain document/table order. Retain the workbook's full markdown catalog; documents with no selected table have an empty `tables` list.

Retain an independent requested-document/catalog cap under the existing dataset budget, authorize all requested documents, then filter tables before the selected-table count limit and value scans. Preserve execution capacity, timeout, memory and cancellation controls. The default response remains complete except for the explicitly changed column shape.

### 2. Separate stored classification from the compact response

Keep the stored categorical verdict readable for old and new artifacts; it avoids scanning every string column to reclassify on every description. Do not expose that internal verdict in tool responses. Stop computing/writing the unused two-value flag while tolerating old metadata containing it. Keep exact current categories computed at description time, not persisted category values.

The response has `name`, `dtype`, optional `categorical_values` for categorical string columns, and `min_value`/`max_value` only for integer/float columns. A numeric column with no finite values retains null bounds under the existing contract. Omit unrelated null fields in column descriptions and nullable optional table/document metadata. A classified categorical string whose current values are empty returns `categorical_values: []`; absence of the field means it is not described as categorical. Dates never expose categories. Update all current tool responses sharing column schemas, not just one serializer branch.

Use a small explicit response projection/model rather than deleting classification metadata or adding repeated full-data inference. Keep the old trace shape readable in the frontend while new responses emit only the compact shape. Update both tabular prompts and regenerate Knowledge Flow OpenAPI/client using existing commands.

### 3. Preserve dates at ingestion, not through a false response label

Keep recognized date columns as pandas temporal dtypes into Parquet. Use `datetime` for the API vocabulary and physical DATE/TIMESTAMP-family types for stored/queryable values. Validate all non-empty values before converting a column; partial 70-percent date guesses must not silently replace invalid cells with null. Ambiguous or incompatible mixed text remains text without losing its original non-empty values. Preserve established timezone semantics; do not silently invent UTC or a day/month interpretation. Preserve the extractor's configured no-coercion mode.

Reuse current CSV native inference and type mapping, and verify parity. No per-query casting of all stored strings or unconditional conversion based on column names. Historical VARCHAR artifacts remain truthfully described as strings until explicit source reprocessing; update migration guidance instead of silently rewriting them.

### 4. Enrich only the existing curated SQL diagnostic

At the existing query execution boundary, classify supported unknown/ambiguous-column binder failures and build a bounded safe message from the validated SQL and mounted tables' schema metadata. Resolve SQL aliases to those tables. Offer a column candidate only if it is visible in the failing query scope. In complex CTE/subquery projections where that cannot be proved, retain the safe original diagnostic without speculative suggestions.

For `c.region` with only Commandes referenced, say it is absent from Commandes and show a small bounded list of that table's columns. Do not mention Clients. If Clients is explicitly joined as `cl` and `region` is visible there, the diagnostic can identify `cl.region`. Never scan cell values, open another artifact, expose hidden relation names, infer a join or change the submitted query. Reuse the existing curated `read_query` HTTP 400 path and explanatory drawer; no general provider-error display, new diagnostic event or error framework. Preserve genuine authority-loss and cancellation stops.

### 5. Keep proposal 4 inside the packaged prompt

Add short guidance to qualify column references in JOIN queries and use separate tool calls for independent SQL instructions. Do not change the validator, execution contract, multi-statement errors or add batch execution. Keep existing shipped date guidance unchanged; proposal 5 is excluded.

## Risks / Trade-offs

- Response field removal affects current consumers: regenerate clients and update prompts/UI together, with read-only legacy trace support.
- Human labels can collide: reject ambiguity and require existing exact aliases; SQL identifiers stay unchanged.
- Date conversion can lose data or change meaning: test mixed/invalid/ambiguous values and typed Parquet round trips, not just displayed dtypes.
- Date fixes do not repair omitted business predicates: keep the existing type-aware interval guidance and verify expected KPI values independently.
- Scope leakage through diagnostics: adversarial tests with unreferenced tables, CTEs, quoted identifiers and same-name columns; assert no extra artifact read/mount.
- Scale and replicas: selection and diagnostic construction use bounded request-local work and existing metadata; no cross-request state or locks. Selection reduces scans. No new category scan, connection pool or service is required. Current exact category lists can still be large; do not introduce silent truncation in this slice.

## Migration Plan

Ship updated API/MCP descriptions, packaged prompts and frontend together; document the breaking field replacement and table filter. Existing ingestion metadata remains readable and historical trace responses retain display support. Reprocess affected source spreadsheets deliberately to replace stringified date Parquet artifacts; no automatic bulk reingestion or database migration. Record old/new payload sizes on the same synthetic source and rerun representative failed SQL and numerical assertions. Before readiness, run root quality, the full branch audit and independent correctness/performance reviews. Reconcile, sync and archive the OpenSpec change after implementation and verification. Rollback restores the old response/consumer versions together; correctly typed Parquet dates must remain readable without a destructive downgrade.
