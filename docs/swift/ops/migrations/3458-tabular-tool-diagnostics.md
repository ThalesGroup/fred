---
schema: 1
title: "Compact tabular schemas, preserve dates and explain SQL failures"
impact: minor
configuration: none
configuration_reason: "No configuration keys or defaults change; API consumers and packaged prompts must be upgraded together for the compact schema."
---

## Applicability

Deployments using tabular MCP tools, CSV/Excel ingestion and the chat trace drawer.

## Prerequisites

Adapt custom consumers: `categorical_values` replaces `is_categorical` and
`sample_values`; `has_two_values` is removed. Bounds appear only on numeric
columns. The updated frontend still reads historical trace responses.

## Configuration

No configuration or permission changes. Optional `table_names` selects exact
aliases or unambiguous sheet/title labels; omitted/empty describes all tables.
SQL aliases and document UIDs do not change.

## Upgrade

Deploy the compatible frontend first. Drain active turns as appropriate and
upgrade Knowledge Flow API/ingestion workers and agent pods to the same release,
so compact responses and packaged instructions agree. Restart long-lived local
processes when testing without reload.

New Excel ingestion preserves temporal Parquet types. Existing files stay
unchanged and truthfully typed. Reprocessing an existing source is optional and
deliberate; there is no bulk migration. Development validation explicitly
reprocessed only the synthetic Orion workbook.

## Validation

Describe all tables and then selected tables; verify the complete catalog and
compact columns. Check a newly ingested date column has an actual temporal SQL
type. A failed column query must suggest only already referenced tables. The
trace drawer retains submitted arguments, including table selectors, and the
safe cause without recovery advice. Zero-row success keeps its explicit message.

## Rollback

Roll back API, frontend and agent/worker versions together. Stored classification
remains compatible; temporal Parquet was already supported by the prior dtype
vocabulary. Do not convert correctly typed data back to text. Explicit source
reprocessing is not reverted automatically.

## Limitations

Prompt guidance does not guarantee correct calculations or eliminate redundant
calls. No result cache, duplicate-call suppression, multi-statement execution,
automatic UID substitution or new legacy-date repair policy is added. Complex
SQL scopes retain bounded redacted diagnostics. Token refresh is unchanged.
