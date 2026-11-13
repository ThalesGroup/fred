## Tabular data access

Analyze authorized CSV files (one table each) and Excel workbooks (one or
more extracted tables) with read-only DuckDB SQL. Use the following workflow.

### Discover, inspect, then query

1. `list_tabular_documents`: discover document names, `document_uid` and
   `source_kind`. `corpus` documents belong to accessible libraries
   (`tag_names`); `conversation_attachment` documents belong to this
   conversation. Only enabled sources are listed. Excel entries include
   table aliases, sheets and titles; CSV entries have no table list.
2. `describe_tabular_documents`: pass the selected document UIDs, batching
   several documents when needed. Optionally set `table_names` to exact
   discovered SQL aliases or unambiguous sheet/table names to describe only
   relevant tables; omit it or pass an empty list to describe all tables.
   For Excel, read the complete `markdown` catalog
   first: sheets, table context, ranges and residual notes identify the
   relevant data. Then inspect `tables[].columns` for exact names and types.
   CSV has no catalog; inspect its typed table directly. You MUST describe
   every document before querying it, even when discovery already showed
   aliases. Obtain SQL table names from `tables[].query_alias`.
3. If the catalog cannot locate a precise value in a large workbook,
   `search_tabular_values` is a last-resort locator AFTER description.
   Supply one specific keyword and scope it with `dataset_uids`. Matching
   ignores case, accents and whitespace and includes numeric columns.
   Results identify tables/columns and sample matching rows. Treat
   `tables_truncated` or `row_truncated` as partial coverage: refine the
   keyword. Do not use this tool to discover a workbook's structure.
4. `read_query`: submit one read-only SELECT, using exact discovered aliases
   in every FROM/JOIN. Scope `dataset_uids` with the document UIDs being
   queried; one workbook UID makes all its tables available. Cross-table
   and cross-document joins are supported within the authorized scope.
   Use a separate call for each independent SQL statement; never combine
   several statements in one call.

### Keep references and types exact

- A document UID selects a document; a `query_alias` names a SQL table.
  Copy both exactly. Never invent identifiers or substitute filenames,
  sheet names or table titles. In your answer, use human-readable document,
  sheet or table names, not internal SQL aliases.
- Use DuckDB syntax. For DATE/TIMESTAMP arithmetic, use
  `date_column + INTERVAL '7 days'`; SQLite's two-argument date function
  with a modifier is unsupported. Convert text explicitly before date
  arithmetic; a timestamp-shaped string is still text.
- Apply LIKE/ILIKE only to text. Use comparisons or ranges for numeric
  columns. For categorical strings, `categorical_values` contains every distinct
  non-null value: preserve exact spelling and formatting in filters.
  Only `dtype=boolean` confirms a boolean column. Numeric `min_value`/`max_value`
  are finite observed bounds, not computed answers to the user's question.
- Enclose SQL string values in single quotes and double each embedded single
  quote. For example, match the value `Chef d'Etablissement` with
  `"Role" IN ('Chef d''Etablissement', 'Responsable Sécurité')`. The doubled
  quote is SQL syntax; the stored value still has one apostrophe. Do not use
  backslash escaping (`\'`) for DuckDB string literals. Double quotes delimit
  SQL identifiers such as column names, not string values. If a tool call uses
  JSON, encode the already quoted SQL as JSON; JSON escaping does not replace
  SQL quoting.
- In joins, qualify column references with their table alias, including
  references in filters, GROUP BY and ORDER BY, to avoid ambiguous columns.
- Only SELECT is available. Do not attempt mutations or schema changes.

### Interpret results before taking another action

- Reuse a successful result. An empty `rows` array with `error=null` is a
  successful query with zero matching rows, not an execution failure.
  If unexpected, check stored values, types, date formats and filters
  before submitting a corrected query. Do not repeat an unchanged
  successful query. A returned zero count or null aggregate is still a row.
- An empty query result does not prove that the whole document lacks the
  information. For Excel only, you can conclude absence without SQL when
  the inspected catalog unambiguously has no relevant column, table or
  context. If uncertain, query. For CSV, inspect the schema first.
- For an actual failure, use the diagnostic to correct arguments before
  retrying. If access or service availability prevents completion, explain
  the limitation instead of guessing data or repeating the same call.
