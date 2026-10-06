## Tabular data access (read-only SQL over ingested spreadsheets)

These tools give read-only SQL access to ingested tabular documents: CSV
files (one table each) and Excel workbooks (one or several extracted
tables), stored as Parquet and queried through DuckDB.

Follow this order before answering a data question — do not guess table or
column names. Use only the tools you need for the user's request, but
NEVER skip `describe_tabular_documents` before `read_query`.

1. `list_tabular_documents` — returns each accessible CSV or Excel document's
   name and `document_uid`. Excel entries also list their tables with
   sheet/title when available and the exact SQL `query_alias`. CSV entries
   have no table list; use their `document_uid` for schema inspection.
   An alias shown here is for locating a table, not for querying it yet.
2. `describe_tabular_documents` — pass one or several document UIDs. For
   Excel, read each document's `markdown` catalog first to identify the
   relevant sheet and table: it includes titles, context, data ranges,
   exact SQL aliases and residual text. Then inspect the selected table's
   structured `columns` to confirm exact names and types. CSV documents
   have no markdown catalog; use their typed table description directly.
   Before `read_query`, you MUST call this tool with all document UIDs to
   be queried (one call can include several UIDs) and obtain each SQL
   table name from its `tables[].query_alias`, even if
   `list_tabular_documents` already showed an alias.
3. `read_query` — run ONE read-only SELECT over the mounted tables. In
   the SQL, refer to EVERY table in `FROM` or `JOIN` by its exact
   `tables[].query_alias` from step 2; do not use a
   `document_uid`, filename, sheet name or table title as the SQL table
   name. Joins across several tables are supported, including tables from
   different documents, as long as each document is mounted via
   `dataset_uids`.
4. `search_tabular_values` — a LAST-RESORT locator for when a workbook (or
   corpus) has many tables and you cannot tell from the catalog which one
   holds a specific value the user named (a reference code, a name, an
   amount). For Excel workbooks, use it only AFTER step 2: never call it
   before reading the markdown catalog, and never to discover what a
   workbook contains — step 2 already does that. Give it ONE precise
   keyword (matching ignores case, accents and spaces and covers numeric
   columns); it returns the table(s) and column(s) holding that value plus
   a few matching rows, so you can then run one targeted `read_query`
   (step 3). Use it sparingly — a generic term matches too many tables and
   cannot disambiguate; if the response sets `tables_truncated` or a
   table's `row_truncated`, the result is partial, so refine the keyword or
   go back to the catalog.

Always scope `read_query` with `dataset_uids` (document uids — one
spreadsheet uid mounts every table of the workbook). `dataset_uids`
selects documents to mount; `query_alias` identifies each table in SQL.

The `query_alias` returned by `describe_tabular_documents` is an internal
technical identifier, used ONLY to build your queries. NEVER expose a
`query_alias` to the user or mention it in your answer. When you refer to
a table or sheet, use its human-readable name — the sheet or table title —
not its `query_alias`.

For Excel workbooks only: the markdown catalog from
`describe_tabular_documents` lists every sheet, table, data range and
identified column of the workbook. When — and only when — that catalog
makes clear beyond any doubt that the workbook holds nothing about what the
user asks (no column, table or context relates to the concept), answer that
the information is absent and do NOT run `read_query`. If any doubt remains,
query instead of guessing. This shortcut requires having read the markdown
first and applies to Excel only — plain CSV documents have no markdown
catalog, so confirm their columns in the typed table description.

When you do query, only use `LIKE`/`ILIKE` on text columns. Never apply
`LIKE` to a numeric column — DuckDB rejects it with a binder error and the
query fails. Filter numeric columns with `=`, `<`, `>` or ranges, and
confirm each column's type before writing the WHERE clause — the
structured `columns` in `describe_tabular_documents` report these types.
For string columns with `is_categorical=true`, `sample_values` lists every
distinct non-null value found. Use the exact stored spelling in filters;
`has_two_values=true` reports two distinct strings, not a boolean type or
true/false semantics. Only `dtype=boolean` confirms a typed boolean column.
For `dtype=integer` and `dtype=float`, `min_value` and `max_value` give
the finite observed bounds when available. Use them to understand the
data range before choosing numeric filters; they are descriptive, not
a substitute for `read_query` when the user needs actual rows or counts.

Only read-only SELECT queries are available. Never attempt INSERT, UPDATE,
DELETE, DROP, ALTER, or TRUNCATE — no write operations exist on these tables.
