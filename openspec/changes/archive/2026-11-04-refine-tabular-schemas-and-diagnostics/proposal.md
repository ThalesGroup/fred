## Why

The follow-up to [#3458](https://github.com/ThalesGroup/fred/issues/3458) reproduced 28 remaining SQL failures. Schema responses carry redundant fields, Excel dates become strings before Parquet export, and column diagnostics do not identify usable corrections within the SQL's actual table scope.

## What Changes

- Add optional explicit table selection to `describe_tabular_documents`; omission or an empty selection retains today's all-tables behavior and the workbook catalog.
- **BREAKING**: replace response fields `is_categorical` and `sample_values` with optional `categorical_values`, remove `has_two_values`, and expose numeric bounds only on integer/float columns. Preserve current exact category values and numeric-bound calculation.
- Preserve established temporal types from Excel extraction through Parquet and expose the existing API dtype `datetime`. Do not label existing VARCHAR artifacts as typed dates without rewriting them from their source.
- Enrich curated SQL column diagnostics using only datasets actually referenced in the validated query and columns visible in its failing SQL scope. Never load or inspect another table to suggest a correction.
- Update supported schema consumers, prompts, generated clients and the existing explanatory error display together; retain historical trace readability.

No UID binding, alias simplification, automatic SQL repair, new retries, caching, duplicate-call suppression or authorization change. Proposal 4A/4B is approved strictly as packaged-prompt guidance (qualified JOIN columns and one SQL instruction per call). Proposal 5 is rejected: no additional legacy-date detection, conversion guidance or business-filter policy is introduced.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `tabular-document-description`: optional exact table selection, compact column responses and reliable temporal types.
- `tabular-query-safety`: actionable, bounded column diagnostics confined to the query's referenced and mounted tables.

## Impact

Knowledge Flow tabular models/controller/service/artifact helpers, Excel extraction/export, MCP instructions, frontend tabular trace rendering, generated OpenAPI/client, focused tests and migration guidance. Existing stored classification metadata remains readable; already stringified dates require explicit reprocessing. No new database table, shared state, service, dependency or tool is introduced. Implementation remains on the existing user-selected branch; the developer explicitly approved implementation of points 1, 3 and prompt-only 4A/4B on 2026-11-04, followed by targeted synthetic-workbook reingestion and the frozen 32-case campaign.
