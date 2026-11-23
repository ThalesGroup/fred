## Why

A user message does not show which files were sent with it, live or after reload: attachments only reach the runtime as `runtime_context.attachments_markdown`, which lists every session attachment. Issue #3488.

## What Changes

- Add optional `RuntimeContext.attachments: [{attachment_id, name, mime?}]`, holding only this turn's ready attachments.
- The runtime stores it on the user message as `metadata.extras.attachments`.
- The user message bubble shows them as read-only chips (file icon, name), live and after reload.
- `attachments_markdown` is unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `managed-conversations`: user messages show their own attachments.

## Impact

fred-sdk `RuntimeContext`, fred-runtime `_write_turn_history`, regenerated runtime client, chat send path, history mapping, `UserMessage` and a `Chip` appearance. No migration of stored data; older messages and older pods are unaffected.
