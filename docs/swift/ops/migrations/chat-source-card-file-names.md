---
schema: 1
title: "Show file names in chat source cards"
impact: none
configuration: none
configuration_reason: "Only the frontend's chat source card label changes; no configuration keys or defaults change."
no_action_reason: "Existing search results and stored metadata remain unchanged; the new label appears after a normal frontend deployment."
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

Open a chat answer with vector search sources. A source card should show the document's file name even when the PDF title is `(anonymous)`.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The source detail panel continues to show the document's stored title and author metadata.
