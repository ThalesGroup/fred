---
schema: 1
title: "Recall sent messages in the chat composer with the arrow keys"
impact: none
configuration: none
configuration_reason: "Frontend keyboard behaviour only; no configuration key, chart value or permission changes."
no_action_reason: "The recall list is built from the conversation already loaded in the page; no API, stored data or runtime change."
---
## Applicability

All Fred deployments using managed chat.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

In a conversation with sent messages, press the up arrow in the empty composer:
the last sent message comes back, and a message sent through a `/command`
comes back as its `/command` line.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Only the message text is recalled; attachments and turn options are not.
