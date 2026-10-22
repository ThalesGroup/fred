---
schema: 1
title: "Remove the background gradient around the initial chat composer"
impact: none
configuration: none
configuration_reason: "Only frontend styling for the empty managed-chat state changes; no configuration keys or defaults change."
no_action_reason: "The UI change takes effect with normal deployment; data and APIs are unchanged."
---

## Applicability

Existing Fred deployments using managed chat.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Open a new empty conversation and confirm the chat input has no background fade around it.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
