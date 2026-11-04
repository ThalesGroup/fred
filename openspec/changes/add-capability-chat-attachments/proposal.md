# Let capability plugins keep - and forget - files attached in the chat

Tracking: none yet - proposed from a downstream fork for upstream review.

## Why

The platform keeps no bytes of a file attached in the chat: it ingests it for
search and keeps a summary. A capability that must work on the file itself -
`word_template` making an attached Word file the document's base, or placing an
attached image in the document - has no way to get the bytes once the message
is sent.

A copy taken at attach time raises the reverse problem: when the user removes
the file from the chat before sending, the platform deletes its own record,
but the capability's copy stays, and the agent keeps seeing a file the user
withdrew. This was observed live: the agent announced a file the user had
removed before sending.

Separately, a capability config form could stage only one file per asset slot,
while a template library needs several.

## What Changes

- **New optional plugin hook `onChatAttachment(file, context)`** on
  `CapabilityUiPlugin`. The chat calls it once per file attached in a session
  where the capability is active, in parallel with the normal ingestion and
  before the attachment turns ready, so a message sent right after already
  sees it. Best-effort: a rejection is logged and never fails the attachment.
  `context` carries the capability id, its ingress base URL, the team id and
  the session id.
- **The hook may return a "forget" callback.** The chat calls it when the user
  removes that file - including a removal that lands before the capability has
  answered - so the capability's copy goes with it.
- **A small registry** resolves handlers by capability id
  (`chatAttachmentRegistry.ts`), mirroring the approval-renderer registry.
- **Multi-file asset slots**: a config widget may stage several files for one
  slot (`StagedAssetFile = File | File[]`); the agent save sends them as
  repeated `asset_slots` / `asset_files` multipart entries, in order, which the
  control plane already pairs. `FileDropzone` gains a multi-file mode
  (`onFiles` + `multiple`) and a `disabled` state; its props require exactly
  one of `onFile` / `onFiles`.

## Capabilities

### New Capabilities

- `capability-chat-attachments`: how a capability plugin receives the files
  attached in the chat, how its copy follows a removal, and how a config
  widget stages several files for one asset slot.

### Modified Capabilities

<!-- None. -->

## Impact

**Frontend**

- `features/capabilities/types.ts` - `ChatAttachmentContext`,
  `ChatAttachmentForget`, `CapabilityChatAttachmentHandler`, the optional
  plugin field.
- `features/capabilities/chatAttachmentRegistry.ts` - handler registry.
- `components/pages/ManagedChatPage/useChatAttachments.ts` - calls the
  handlers, keeps their forget callbacks per attachment, calls them on removal.
- `components/shared/molecules/FileDropzone` - multi-file mode.
- Agent form (`AgentFormModal`, `AgentFormBody`, `CapabilityCard`,
  `TeamAgentsPage`) - staged file lists per slot.

**Backends**

- None for the hook. Each capability serves its own upload and delete routes
  (for `word_template`: see `add-word-template-engine`).

**Contracts and docs**

- `docs/swift/capabilities/AUTHORING.md` and the `add-fred-capability` skill
  describe the hook; migration note `chat-attachment-capability-hook.md`.
- No frozen contract changes.
