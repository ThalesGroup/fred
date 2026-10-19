# Proposal

## Why

Deep agents need to write a file, present it for human review, and let a later parent or subagent continue from the user's saved edits without copying the document into another store or loading it into the parent's context. The temporary [#2804](https://github.com/ThalesGroup/fred/pull/2804) importer breaks that round trip; this change delivers the filesystem-backed workflow in [#2706](https://github.com/ThalesGroup/fred/issues/2706).

## What Changes

- Provide `open(path)` as a standard Deep runtime tool for parents and native subagents, with no optional capability to enable and no implicit execution pause.
- Open the current filesystem file in the chat side panel: the existing Markdown editor and Word export, the existing restricted static HTML preview plus editable source, or a CodeMirror text editor. Bundle syntax-highlighting languages with Fred for air-gapped use.
- Save edits to the same conversation filesystem, refresh open views after writes, preserve unsaved buffers, and finish pending editor saves before starting the next user turn.
- Record non-agent changes between consecutive user-turn starts, including edits made during execution. Consolidate consecutive external edits, split around parent/subagent writes, and retain full unified diffs under `/.deep/changes/<turn-id>/`.
- Notify the agent at turn start with a changed-file count and a bounded list of diff paths, never inline document or diff content. A truncated list points to the directory for `ls`; no `index.json` is introduced.
- Remove the temporary `open_writable_document` capability and its copy/import path. Keep the existing ReAct writable-document and HTML capabilities, documents, tables, APIs, and historical views. Do not migrate existing documents.
- Keep current write/edit/concatenation semantics. Overwrite guardrails, custom iframe viewers, capability UI packaging, dashboards, CSV editing, and PDF viewing are deferred.

## Capabilities

### New Capabilities

None. This is a follow-on to the completed implementation tracked by `add-deep-agent-conversation-filesystem`, not a second filesystem implementation.

### Modified Capabilities

- `managed-conversations`: Add filesystem file presentation, editing, refresh, export, change notifications, and compatibility requirements to the existing conversation surface.

## Impact

- `fred-sdk`: a typed built-in file-reference UI part and the minimal filesystem/change contracts needed by runtime and generated clients.
- `fred-runtime`: standard Deep tool/middleware assembly, conversation-bound file access, change recording, turn-start publication, and reuse of existing storage and erasure.
- Frontend: native file viewers, authenticated runtime API integration, child-tool UI-part propagation, save/refresh coordination, and locally served CodeMirror language chunks.
- Writable-document package and runtime registration: remove the bridge while reusing Markdown export and preserving the ReAct path. Deep agents no longer need document/HTML capability selection for these outputs.
- The implementation follows the confirmed scope, which supersedes the issue's older proposals to migrate/delete legacy documents, inject inline diffs, and enforce read-before-overwrite. Those are not acceptance criteria for this delivery.
