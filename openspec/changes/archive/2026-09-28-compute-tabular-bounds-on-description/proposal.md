## Why

`describe_tabular_documents` currently relies on categorical values and numeric bounds captured during ingestion. Documents imported before bounds were stored, including the reported Excel workbook, show null bounds even though their Parquet tables contain numeric values. The bug is that the tool does not read the values it is describing at call time.

Tracking issue: [#2819](https://github.com/ThalesGroup/fred/issues/2819).

## What Changes

- Read exact distinct non-null categories for columns classified as categorical, and compute finite non-null minimum and maximum values for integer and float columns, during each `describe_tabular_documents` call for both CSV and every table in an Excel workbook.
- Keep categorical identification (`is_categorical`, `has_two_values`) and numeric typing in CSV and Excel ingestion, but stop storing category samples and numeric bounds there. Ignore historical stored values when producing a description.
- Keep null bounds for numeric columns with no finite values, and preserve the existing catalog, classifications, types, document order, and access checks.
- Run the reads through the existing bounded DuckDB execution path and report artifact failures through the existing safe error handling.

## Capabilities

### New Capabilities

- `tabular-document-description`: Describes authorized CSV and Excel documents with categorical values and numeric bounds read from their queryable Parquet tables at tool call time.

### Modified Capabilities

None. No current OpenSpec capability covers tabular document descriptions.

## Impact

- Knowledge Flow backend tabular description service, CSV and Excel ingestion processors, their tests, and the current tabular design documentation.
- The response shape and agent-facing tool name stay the same; calls that previously used stored category samples or numeric bounds will instead return values from the current Parquet artifact.
- Description calls will read table data and may take longer for large documents; the existing execution limits must govern this work.
