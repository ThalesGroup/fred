# fred-capability-writable-document

Fred agent capability that co-authors a session-scoped Markdown document from chat.

The agent first calls `begin_document_generation(title)` with a short title,
waits for its acknowledgement, then composes the content and calls
`write_document` in a later model round to create or revise a deliverable
(report, email, memo, meeting notes) that is kept OUT of the conversation stream
and shown in a dedicated editor pane. The user can edit the document back, and
export it to Word (`.docx`) or Markdown. Documents are scoped to one chat
session and co-authored over time by the agent and the user; only the last
author is tracked.

Preparation publishes no document and performs no store write. The trace shows
content generation while the model composes the payload, then document writing.
Direct `write_document` calls remain supported, and revisions reuse the existing
`document_id`. Importing existing workspace Markdown with `open_writable_document`
does not need a preparation call. See the
[deliverable generation spec](../../../openspec/specs/deliverable-generation/spec.md).

This package is a Swift port of Kea's "Writable Document" feature (GitHub issue
#1905): the editor feature is one `AgentCapability` — the `write_document`
middleware (static tool + user-edit notification + open-documents catalog
prompt), one owned table (`cap_writable_document_docs`), the contributed
`writable_document` chat part, the editor side panel, and the list/get/put/export
router.

The package also registers a separately enabled, temporary
`open_writable_document` capability for Deep Agent demos. Its sole tool copies
an existing Markdown file from any readable mount in the current conversation
workspace into the editor. Enable both capabilities on the demo agent:
`writable_document` owns the editor and `open_writable_document` adds the import
tool. The copied document can be edited, but those edits do not update the
source workspace file.

## Registration

Installing this package *is* the registration: the fred-agents pod auto-discovers
the capability at boot via the `fred.capabilities` entry point declared in
`pyproject.toml`
(`writable_document = "fred_capability_writable_document.capability:WritableDocumentCapability"`).
The second entry point registers `open_writable_document` independently.
