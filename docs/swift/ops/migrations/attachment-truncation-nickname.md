---
schema: 1
title: "Use the configured agent nickname in attachment truncation notices"
impact: none
configuration: none
configuration_reason: "Only frontend wording changes; no configuration keys or defaults change."
no_action_reason: "Existing attachments and APIs are unchanged; the notice uses the configured nickname after normal deployment."
---
## Applicability

Swift deployments with a custom agent nickname and conversation attachments.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Configure a custom agent nickname, then attach a text document that exceeds
the ingestion limit. The upload warning and saved preview should use that
nickname instead of "Fred".

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Notices already saved in attachment previews retain their previous wording.
