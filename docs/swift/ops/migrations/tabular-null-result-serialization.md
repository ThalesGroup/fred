---
schema: 1
title: "Serialize missing CSV and Excel result cells as JSON null"
impact: none
configuration: none
configuration_reason: "Only tabular result conversion changes; configuration keys, defaults and API schemas are unchanged."
no_action_reason: "Existing CSV and Excel artifacts remain usable. Missing cells are normalized when results are returned, without re-ingestion, data migration or client updates."
---
## Applicability

Deployments using tabular SQL queries or keyword searches over CSV and Excel.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. Existing source documents and Parquet artifacts do not
need to be changed or re-imported.

## Validation

Query a CSV row containing a missing typed date, or query an Excel date column
using a nullable DATE/TIMESTAMP expression. The result must succeed with a JSON
null cell and retain the other values and rows. Search for a value in a CSV row
with a missing date and confirm the result also succeeds.

## Rollback

Use the normal rollback procedure. No stored data is changed; rolling back can
restore the previous serialization failures on nullable date results.

## Limitations

This change does not alter Excel extraction/type policy or model-generated
queries and answers. It normalizes missing values in returned tabular rows.
