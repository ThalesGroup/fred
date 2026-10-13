---
schema: 1
title: "Decode Windows-1252 and BOM-prefixed plain-text and Markdown inputs"
impact: none
configuration: none
configuration_reason: "Only the decoding inside the plain-text and Markdown input processors changes; no configuration keys or defaults change."
no_action_reason: "New ingestions and attachments are decoded correctly with normal deployment; previously failed uploads can simply be uploaded again, nothing has to be reprocessed for the upgrade."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Ingest a `.txt` file saved as Windows-1252 ("ANSI") containing accented words,
and check that ingestion succeeds and the preview keeps the accents.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Plain-text and Markdown files ingested before this release with accents
stripped (chat attachments) or that failed to ingest are not repaired
automatically; upload them again if needed.
