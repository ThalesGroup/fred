---
schema: 1
title: "Prefer direct attachment reading and disclose truncation"
impact: none
configuration: none
configuration_reason: "Only existing tool guidance and tool-result truncation notices change; limits and capability settings are unchanged."
no_action_reason: "Existing storage and API fields are reused without a schema change or reprocessing requirement; normal deployment applies the correction."
---
## Applicability

Weaver deployments supporting conversation attachments.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required. Existing capability choices still govern
whether the agent can read documents or query tabular datasets.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

For an answer beyond the first read portion of a text attachment, verify that the
agent continues with the returned offset rather than immediately switching to RAG.
Check that tool-reported truncation is disclosed without claiming completeness.
CSV and Excel remain on Weaver's existing tabular path.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.
Stored attachment data is unchanged.

## Limitations

Tool selection remains model-driven. Conversion limits, OCR behavior and context
budgets are unchanged. Swift upload-toast and persisted-preview warnings are not ported here: Weaver uses
CP/Temporal ingestion, not Swift fast-ingest. That UI behavior remains an explicit
follow-up requiring authoritative truncation facts; no legacy endpoint is restored.
