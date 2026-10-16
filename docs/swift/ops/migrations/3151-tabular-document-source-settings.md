---
schema: 1
title: "Honor saved document source settings in tabular tools"
impact: none
configuration: none
configuration_reason: "The runtime now uses existing saved agent tuning when configuring tabular tools; no configuration keys or defaults change."
no_action_reason: "Existing agent settings take effect after normal deployment; no data migration, re-ingestion or manual update is needed."
---

## Applicability

Deployments using tabular tools with agent document access restricted to attachments or team documents.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required. Existing agent document source settings are preserved.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

With an agent configured for attachments only, list tabular documents in a conversation that has an Excel attachment while its team corpus also contains an Excel file. The list should contain the attachment and exclude the corpus file.

## Rollback

Use the normal rollback procedure; this change introduces no data migration. A rollback restores the previous behavior, which may list corpus files despite an attachments-only setting.

## Limitations

No additional migration limitations identified for this change.
