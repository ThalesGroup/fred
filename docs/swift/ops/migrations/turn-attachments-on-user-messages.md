---
schema: 1
title: "Show the attachments sent with each user message"
impact: none
configuration: none
configuration_reason: "Only an optional runtime context field and its chat rendering change; no configuration key, chart value or default changes."
no_action_reason: "The field is optional in both directions: older pods ignore it, and stored messages without it render as before, so no data migration or deployment order is needed."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required. Agent pods built on an older fred-runtime keep working but do not store the files, so their reloaded messages show no chips.

## Validation

Send a chat message with two attached files and check that the message shows both file names as chips, then reload the conversation and check that the chips are still there.

## Rollback

Use the normal rollback procedure; this change introduces no data migration. Stored `metadata.extras.attachments` values are ignored by older frontends.

## Limitations

Messages sent before this release have no stored attachment list and show no chips. A message needs text to be sent: files alone were already rejected by the runtime, and the composer now keeps them until text is added.
