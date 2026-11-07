---
schema: 1
title: "Show attachments on user messages"
impact: none
configuration: none
configuration_reason: "Only the chat display changes, in the frontend; no configuration key, chart value or default changes."
no_action_reason: "The display derives from the attachment list the Control Plane already serves; no contract, service or stored data changes."
---
## Applicability

Fresh Fred installations.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Install Fred normally; no additional operator or user action is required.

## Validation

Send a chat message with two attached files and check that the message shows both
file names as chips, then reload the conversation and check that they are still there.

## Rollback

Use the normal rollback procedure; this change stores no data and introduces no
migration.

## Limitations

The placement relies on dates and does not prove which turn used a file. A deleted
file disappears from its message. A message requires text: the composer keeps files
until text is added.
