---
schema: 1
title: "Prefer direct attachment reading and disclose truncation"
impact: none
configuration: none
configuration_reason: "Only existing tool guidance, truncation notices and attachment preview feedback change; limits and capability settings are unchanged."
no_action_reason: "Existing storage and API fields are reused without a schema change or reprocessing requirement; normal deployment applies the correction."
---
## Applicability

Swift deployments supporting conversation attachments.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required. Existing capability choices still govern
whether the agent can read documents or query tabular datasets.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Attach a text document exceeding the ingestion limit: a notice appears on upload,
remains in its preview after reloading, and precedes the text returned by direct
reading. Check a factual question and a question needing later portions. A CSV
with a shortened preview must remain queryable without a missing-data warning.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.
Notices already saved in attachment previews remain readable.

## Limitations

Tool selection remains model-driven. Conversion limits, OCR behavior and context
budgets are unchanged. Previously stored previews are not rewritten; legacy
attachments without truncation metadata cannot be diagnosed retrospectively.
