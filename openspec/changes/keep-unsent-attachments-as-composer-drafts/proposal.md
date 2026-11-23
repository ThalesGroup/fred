## Why

Issue #3502. A file dropped in the composer but never sent leaks into another conversation with the same agent, and is lost from the composer when the user leaves its conversation and comes back. The drawer and the agent context already list it as if it had been sent.

## What Changes

- An attachment counts as sent once a user message lists it in `metadata.extras.attachments`, or when it was created before the latest composer message without that list. New turns record an empty list when no files are sent.
- Every other attachment of the conversation is a composer draft: shown only in its own conversation's composer, restored there on return, sent with the next message.
- The attachments drawer, its count and `attachments_markdown` list only sent attachments, plus the files of the turn being sent.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `managed-conversations`: unsent attachments are composer drafts of their conversation.

## Impact

Frontend draft handling and runtime user-message metadata. No control-plane field, migration, or generated client change.
