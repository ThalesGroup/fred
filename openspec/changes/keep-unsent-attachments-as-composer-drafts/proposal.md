## Why

Issue #3502. A file dropped in the composer but never sent leaks into another conversation with the same agent, and is lost from the composer when the user leaves its conversation and comes back. The drawer and the agent context already list it as if it had been sent.

## What Changes

- An attachment counts as sent once a user message carries it (`metadata.extras.attachments`), or when it was created before the conversation's latest user message (messages stored before #3488 carry no list).
- Every other attachment of the conversation is a composer draft: shown only in its own conversation's composer, restored there on return, sent with the next message.
- The attachments drawer, its count and `attachments_markdown` list only sent attachments, plus the files of the turn being sent.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `managed-conversations`: unsent attachments are composer drafts of their conversation.

## Impact

Frontend only: `useChatAttachments.ts`, its call sites in `useManagedChat.ts`, and tests. No control-plane field, no migration, no generated client change. Overlaps `useChatAttachments.ts` with open PRs #3499 and #3500; the conversation filter #3500 adds becomes part of this change.
