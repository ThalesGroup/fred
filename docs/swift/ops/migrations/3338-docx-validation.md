---
schema: 1
title: "Validate DOCX during metadata extraction"
impact: none
configuration: none
configuration_reason: "The existing DOCX processor and upload error handling change; no settings, defaults, chart values or API fields change."
no_action_reason: "Normal deployment applies the validation fix to subsequent uploads without changing stored documents or requiring reprocessing."
---
## Applicability

Existing Fred deployments ingesting Word documents.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator action is required.

## Validation

Upload a readable DOCX and confirm metadata preparation succeeds. Upload an
invalid DOCX and confirm the progress error explains how to save or export a
readable copy without displaying a server temporary path.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

This fix does not guarantee that an oversized document fits in worker memory.
Kernel OOM kills cannot be caught as Python exceptions. Optional classification
guardrails and Pandoc retain their existing separate reads.
