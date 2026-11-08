---
schema: 1
title: "Unsent chat attachments stay drafts of their conversation"
impact: none
configuration: none
configuration_reason: "Frontend-only change to the chat composer; no configuration keys or defaults change."
no_action_reason: "Attachment rows and APIs are unchanged; whether an attachment was sent is derived from the stored user messages."
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

Drop a file in a conversation without sending a message, then open another conversation with the same agent: its composer does not show the file. Come back: the file is in the composer, not in the attachments drawer. Send a message: the drawer now lists it.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Knowledge Flow indexes a file as soon as it is dropped, so a file dropped during a running turn can be found by that turn's document search.
