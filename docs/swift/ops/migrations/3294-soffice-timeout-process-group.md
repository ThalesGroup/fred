---
schema: 1
title: "Kill the whole LibreOffice process tree when an Office-to-PDF conversion times out"
impact: none
configuration: none
configuration_reason: "Only how fred-core starts and stops the soffice subprocess, and how the Knowledge Flow extraction child sweeps its helpers, change; no configuration key, default or chart value is touched."
no_action_reason: "No data, API or deployment order changes; a conversion that times out now stops soffice.bin with it instead of leaving it running, which takes effect with the normal deployment."
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

After an Office-to-PDF conversion has timed out (a `[OFFICE2PDF] LibreOffice conversion timed out` log line in fred-agents or Knowledge Flow), `ps -ef | grep soffice.bin` in that pod shows no leftover LibreOffice process.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
