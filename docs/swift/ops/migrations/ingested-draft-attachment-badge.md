---
schema: 1
title: "Show ingested draft attachments in conversation files"
impact: none
configuration: none
configuration_reason: "Only the frontend attachment count and drawer change; configuration is unchanged."
no_action_reason: "Existing attachment rows and APIs are unchanged; normal deployment makes ingested drafts visible."
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

Attach a file without sending a message. After ingestion completes, the folder badge shows one and the conversation drawer lists the file, including after a page reload.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The badge counts persisted attachment rows. Ingestion in progress and failed uploads are not counted.
