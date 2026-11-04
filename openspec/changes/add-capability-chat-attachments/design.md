# Design - Let capability plugins keep - and forget - files attached in the chat

## Context

See `proposal.md` - Why. Facts that shaped the design:

- The chat (`useChatAttachments`) already ingests each attached file and
  persists a session attachment record in the control plane; it keeps no
  bytes after that.
- Capability plugins are resolved by capability id for other extension points
  (side panels, config widgets, approval renderers).
- The control plane already pairs repeated `asset_slots` / `asset_files`
  multipart entries into one ordered list per slot; only the frontend staged a
  single file.

## Goals / Non-Goals

**Goals:**

- A capability gets the bytes of an attached file without a platform store.
- The user's removal of a file reaches the capability's copy.
- No effect on the chat when no active capability declares a handler.

**Non-Goals:**

- Any backend or contract change.

## Decisions

### 1. A plugin hook, not a platform route

Each capability uploads to its own route (it already owns its storage and
routes). The platform only hands over the file. Rejected: a platform-side
store for capability files - a new platform responsibility for a need two
capabilities share.

### 2. Called before the attachment turns ready

The handler runs in parallel with ingestion, and the attachment turns ready
when both are done; sending is blocked while an attachment is not ready, so a
message never reaches the agent before the capability has the file.

### 3. Forget as a returned callback

The handler returns how to undo itself. The chat keeps the callbacks per
attachment id and calls them on removal; a removal that lands first is
remembered and applied when the callback arrives. Rejected: a second plugin
hook keyed by file name - names are not unique, and only the handler knows the
id its own backend assigned.

### 4. Best-effort everywhere

A failing handler or forget callback is logged, never surfaced as an
attachment failure: the platform's own handling of the file does not depend
on any capability.

## Migration Plan

Additive frontend change; plugins without the hook are unaffected. Migration
note `chat-attachment-capability-hook.md` (no operator action).

