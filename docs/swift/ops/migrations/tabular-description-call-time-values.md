---
schema: 1
title: "Fix categorical values and numeric bounds in tabular descriptions"
impact: none
configuration: none
configuration_reason: "The description and ingestion code change without adding configuration keys, permissions, or deployment settings."
no_action_reason: "Existing CSV and Excel Parquet artifacts can be read by the description tool; no re-ingestion, metadata migration, client update, or special deployment order is needed."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. Existing tabular documents gain call-time category values and numeric bounds without re-ingestion.

## Validation

Describe an existing Excel workbook with categorical and numeric columns. Confirm the categorical columns list their distinct values and integer/float columns show finite minimum and maximum values.

## Rollback

Use the normal rollback procedure. Older code reads values from ingestion metadata, so documents ingested only while this fix was deployed may show empty category samples or numeric bounds after rollback. Their table data remains available for queries.

## Limitations

Description calls read the selected Parquet tables and remain subject to the configured tabular execution capacity, time, and memory limits.
