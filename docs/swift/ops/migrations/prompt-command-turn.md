---
schema: 1
title: "Record and render a chat turn launched by a prompt command"
impact: none
configuration: none
configuration_reason: "Two optional model fields and one transcript component; no configuration key, default, or chart value changes."
no_action_reason: "No schema change, no data migration, and nothing writes the new field until the composer trigger ships; normal deployment is sufficient."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

A chat turn may now record the prompt command it was launched from:
`RuntimeContext` gains an optional `command`, and the stored turn's metadata
gains the matching key. Both are optional, and the turn's content is unchanged
— it still holds the full text sent to the model. The transcript renders such
a turn as its command, with the prompt one click away in a side panel.

Nothing writes the field yet: the `/` trigger that produces a command turn
ships in a later release. Until then this release changes no user-visible
behaviour.

No database change: conversation history stores message metadata as a JSON
document, which already accepts additional keys.

## Validation

Open an existing conversation and confirm every turn renders exactly as
before. No turn recorded before this release carries a command, so all of them
take the plain-text path.

## Rollback

Use the normal rollback procedure; this change introduces no data migration. A
turn that recorded a command before the rollback renders as its plain text
afterwards — degraded, not broken.

## Limitations

The command cannot yet be typed in the chat; the trigger and its menu ship in
a later change.
