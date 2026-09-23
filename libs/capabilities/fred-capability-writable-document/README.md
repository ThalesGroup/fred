# fred-capability-writable-document

Fred agent capability that co-authors a session-scoped Markdown document from chat.

The agent calls a `write_document` tool to create or revise a deliverable
(report, email, memo, meeting notes) that is kept OUT of the conversation stream
and shown in a dedicated editor pane. The user can edit the document back, and
export it to Word (`.docx`) or Markdown. Documents are scoped to one chat
session and co-authored over time by the agent and the user; only the last
author is tracked.

This package is a Swift port of Kea's "Writable Document" feature (GitHub issue
#1905): the whole feature is ONE `AgentCapability` — the `write_document`
middleware (static tool + user-edit notification + open-documents catalog
prompt), one owned table (`cap_writable_document_docs`), the contributed
`writable_document` chat part, the editor side panel, and the list/get/put/export
router.

## Registration

Installing this package *is* the registration: the fred-agents pod auto-discovers
the capability at boot via the `fred.capabilities` entry point declared in
`pyproject.toml`
(`writable_document = "fred_capability_writable_document.capability:WritableDocumentCapability"`).
