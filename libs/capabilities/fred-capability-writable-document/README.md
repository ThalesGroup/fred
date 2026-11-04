# fred-capability-writable-document

Fred agent capability that co-authors a session-scoped Markdown document from chat.

The agent calls a `write_document` tool to create or revise a deliverable
(report, email, memo, meeting notes) that is kept OUT of the conversation stream
and shown in a dedicated editor pane. The user can edit the document back, and
export it to Word (`.docx`) or Markdown. Documents are scoped to one chat
session and co-authored over time by the agent and the user; only the last
author is tracked.

Word exports set both Author and Last modified by to the authenticated exporter's
verified first and last names when both are non-empty after trimming, otherwise
to their trimmed verified username. If no reliable name is available, including
for delegated `AssertedUser` identities without a profile, both properties are
explicitly cleared. No user ID or workload name is substituted and no directory
lookup is performed. Each property is limited to 255 characters. These export
properties do not change the stored content, ownership or access controls, and
Markdown export remains unchanged. Names supplied by the browser or model are
not accepted as author metadata.

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

The served router is mounted by `create_agent_app` under
`/capabilities/writable_document` with the pod's terms-admission guard. Handlers
use `fred_core.security.oidc.authenticate_request` to bind the effective person,
then filter lists by owner or check the document owner after lookup (404 missing,
403 foreign). Standalone router consumers must supply their own admission guard;
the capability does not import the runtime. The OpenAPI dumper only describes
the router and does not serve requests.
