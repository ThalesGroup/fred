---
schema: 1
title: "Capability plugins can receive files attached in chat, and capability asset slots accept several files"
impact: none
configuration: none
configuration_reason: "Frontend extension point only; no configuration keys, defaults or secrets change."
no_action_reason: "No installed capability declares the new hook yet, and existing single-file asset slots behave as before."
---

## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

A capability's frontend plugin may now declare `onChatAttachment`: the chat
calls it once per file attached in a session where the capability is active,
alongside the normal attachment ingestion. It is best-effort: a failing
handler never fails the attachment. A capability config widget may also stage
several files for one asset slot; they are sent as repeated multipart entries
for that slot, in order. `FileDropzone` gains a multi-file mode (`onFiles`,
`multiple`) and a `disabled` state.

## Validation

Attach a file in a chat and check that it becomes ready as before. On an agent
with the PPT filler capability, upload a template: the analysis runs as before.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The hook only fires when the composer shows its paperclip, that is when a
capability on the agent declares the attach-files chat control (today
`document_access` with its attachments source enabled).
