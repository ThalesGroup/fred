# Spec Delta

## ADDED Requirements

### Requirement: Deep agents present live filesystem files with a standard open tool

Every Deep parent and native subagent SHALL have `open(path)` without an optional capability selection. A successful call SHALL emit a persisted chat UI reference to an existing, authorized conversation file and return a short result identifying its path, selected viewer, and effective editability. It SHALL NOT copy file content into a writable-document record, inject that content into model context, or implicitly pause execution for review. Reopening a historical reference SHALL resolve the current file, not a content snapshot.

#### Scenario: Parent opens a child's output without reading it

- **GIVEN** a native subagent has saved `/report.md`
- **WHEN** the parent calls `open("/report.md")` without first reading its contents
- **THEN** the current Markdown file opens in the conversation's side panel
- **AND** the tool result contains presentation metadata rather than the report body
- **AND** the parent can continue executing

#### Scenario: Native subagent opens a file

- **WHEN** a native subagent calls `open` for a readable file in the shared conversation filesystem
- **THEN** its file reference reaches the user-facing chat and can open the same side panel as a parent call

#### Scenario: Reopen a reference after subsequent edits

- **GIVEN** a file was opened in an earlier turn and has since changed
- **WHEN** the user opens that earlier chat reference after a browser reload
- **THEN** the viewer loads the current file using the original conversation and path
- **AND** a missing file or unavailable runtime produces an explicit localized error instead of stale content or an empty successful view

### Requirement: File viewers preserve existing editing and preview behavior

Markdown files SHALL use the existing Markdown editing experience and support Markdown download and Word export from the current saved file. HTML files SHALL support the existing restricted static preview of one file and an editable source view. Other supported text files SHALL use a source editor with syntax highlighting for common programming, markup, and configuration languages, falling back to plain text for unknown formats. Effective editability SHALL respect the file's access policy; a source editor SHALL NOT make a read-only file writable. Unsupported non-text content SHALL NOT be misrepresented as editable text.

#### Scenario: Export reviewed Markdown

- **GIVEN** the user has saved edits to `/report.md`
- **WHEN** the user exports it to Word
- **THEN** the export uses the updated filesystem content and existing Markdown-to-Word conversion behavior
- **AND** no legacy writable-document row is required

#### Scenario: Edit HTML source while keeping preview restrictions

- **GIVEN** `/page.html` contains styling, scripts, event handlers, and external resource URLs
- **WHEN** the file is previewed
- **THEN** the existing sanitization, sandbox, and content-security restrictions remain effective, including no JavaScript execution or external resource loading
- **AND** preview rendering does not rewrite or sanitize the stored source file
- **WHEN** the user edits and saves the source
- **THEN** the saved HTML file and its restricted preview reflect the change

#### Scenario: Highlight languages without internet access

- **GIVEN** a deployed Fred instance cannot reach the public internet
- **WHEN** the user opens representative Python, JavaScript/TypeScript, HTML/CSS, JSON/YAML, SQL, shell, Java, C/C++, Go, and Rust files
- **THEN** the source editor loads the required highlighting from Fred-hosted assets
- **AND** an unknown text extension still opens as editable plain text when authorized

### Requirement: Editor saves and agent operations share one authoritative file

Successful user saves SHALL update the same conversation file read and written by the parent, native subagents, and filesystem helpers. User editing SHALL remain available while an agent runs. Agent writes SHALL refresh clean open views without another `open` call; late responses SHALL NOT replace a newer view or another conversation's content. Unsaved local edits SHALL survive background refreshes and save failures. After a local save completes, the view SHALL reconcile with the current stored content. This change SHALL preserve existing full-write, exact-text-edit, and explicit concatenation replacement semantics without adding read-before-write guards, locking the editor for the agent's run, or introducing a merge interface.

#### Scenario: Review and delegate continuation

- **GIVEN** the user has edited and saved a report opened by the parent
- **WHEN** the parent starts a new native subagent to continue the work without reading the report itself
- **THEN** the subagent's filesystem read observes the user's saved content

#### Scenario: Agent changes an open file

- **GIVEN** an open editor has no unsaved local changes
- **WHEN** the parent, a child, or `concat_files` completes a write to its file
- **THEN** the side panel refreshes without requiring a reopen or page reload

#### Scenario: Background refresh arrives while the user is typing

- **GIVEN** the user has an unsaved local buffer
- **WHEN** an agent update or a delayed refresh response arrives
- **THEN** the buffer is preserved until its save succeeds or the user discards it
- **AND** an acknowledged save does not clear edits typed while that save was in flight

#### Scenario: Reassemble a large report after review

- **GIVEN** a child has revised one section after user review
- **WHEN** the parent concatenates the sections over the existing report with explicit replacement
- **THEN** it can do so without reading the previous report into its context
- **AND** the open report view refreshes to the saved result

### Requirement: Starting the next user turn flushes pending file edits

Submitting the next user message SHALL finish pending saves for open editors in that conversation before starting its execution and publishing its change notification. A failed save SHALL preserve both the file draft and message draft, report a localized error, and prevent that submission from executing against stale content. Navigation to another conversation SHALL invalidate the pending submission rather than sending it there.

#### Scenario: Send immediately after typing

- **GIVEN** the editor's autosave has not yet completed
- **WHEN** the user submits "continue"
- **THEN** execution starts once, only after the pending edits are saved
- **AND** the first subsequent filesystem read and change notification account for those edits

#### Scenario: Save fails before continuation

- **WHEN** a pending file save fails during message submission
- **THEN** the user's file and message drafts remain available for retry
- **AND** no new agent turn starts

### Requirement: File access respects conversation and mount authorization

File presentation, read, save, refresh, and export SHALL verify the caller's authenticated conversation access and applicable mount/path permissions. A UI part or supplied session/path SHALL NOT grant access by itself. Unknown or foreign conversations, path traversal, and forged references SHALL be rejected without exposing file contents. Runtime-owned `/.deep/` content and other read-only mounts SHALL NOT become writable through an editor or a privileged system-origin filesystem operation.

#### Scenario: Same path in different conversations

- **GIVEN** two conversations contain `/report.md`
- **WHEN** a user opens or saves their authorized conversation's file
- **THEN** only that conversation's file is accessed
- **AND** substituting another user's session identifier is rejected

#### Scenario: Read-only mount opened as text

- **GIVEN** a file is authorized for reading but not user editing
- **WHEN** it is presented through `open`
- **THEN** the tool reports it as read-only and the editor disables saving
- **AND** a direct forged save request is also rejected

### Requirement: External changes are consolidated between user-turn starts

The runtime SHALL record successful non-agent text-file changes made through the conversation filesystem from the start of the previous user turn until the next user turn starts, including edits made while the agent is running. Parent, native-subagent, and agent-invoked helper writes SHALL be excluded from the reported changes; independent background-system writes SHALL be eligible. Internal history writes SHALL be excluded. Consecutive external mutations of the same file SHALL consolidate into a net change; an intervening agent write to that file SHALL end that group. A group with no net content change SHALL produce no diff. Native child invocations and model/tool steps SHALL NOT advance the user-turn boundary.

#### Scenario: Multiple user autosaves

- **GIVEN** the user makes several successful saves to `/report.md` without an intervening agent write
- **WHEN** the next user turn starts
- **THEN** one diff describes the change from before the first save to after the last
- **AND** intermediate autosave steps are not separate artifacts

#### Scenario: External edits surround an agent write

- **GIVEN** `/report.md` changes from A to B externally, from B to C through an agent write, and from C to D externally
- **WHEN** the next user turn starts
- **THEN** the history contains the separate A-to-B and C-to-D diffs in that order
- **AND** it does not attribute the agent's B-to-C change to an external writer

#### Scenario: User edits during execution

- **WHEN** a user saves changes while the parent or a native subagent is running
- **THEN** the saved file is immediately available to later filesystem reads
- **AND** its external change is included at the next user-turn start, with no unsolicited notification during the current run

#### Scenario: Background system changes a file

- **WHEN** an independent background system changes a conversation file through the filesystem service
- **THEN** its net change is eligible for the same history and notification as user edits
- **AND** it is not described as necessarily user-authored

### Requirement: Change history is discoverable as flat diff files

The runtime SHALL publish full unified-diff artifacts directly under `/.deep/changes/<turn-id>/`, where the identifier belongs to the user turn receiving them. A single group for `/report.md` SHALL use `report.md.diff`; multiple groups SHALL use `report.md.001.diff`, `report.md.002.diff`, and subsequent ordered suffixes. Artifact naming SHALL preserve distinct source paths and remain collision-safe. Each diff SHALL identify its exact original virtual file path. The agent SHALL be able to discover all artifacts with ordinary `ls`, `glob`, `grep`, and `read_file`, without an `index.json`, additional document store, shell, or JSON-query tool.

#### Scenario: Flat single and split diffs

- **GIVEN** `/report.md` has one external change group and `/summary.md` has two
- **WHEN** history is published for turn T
- **THEN** `ls("/.deep/changes/T/")` directly exposes `report.md.diff`, `summary.md.001.diff`, and `summary.md.002.diff`
- **AND** the published names and contents are stable when that same turn is retried

#### Scenario: Equal basenames and suffix-like names

- **GIVEN** distinct changed files include nested paths with equal basenames or names resembling a numbered diff suffix
- **WHEN** their diff artifacts are published
- **THEN** no artifact overwrites another
- **AND** each diff's header identifies the original source path without requiring a manifest

### Requirement: Turn-start notifications contain paths rather than content

At user-turn start, the runtime SHALL provide a short notification containing the number of distinct changed source files and a bounded list of their published diff paths. It SHALL NOT automatically include file contents or diff excerpts. Both the path count and total notification length SHALL be bounded independently of document sizes. When truncated, the notification SHALL identify truncation and the complete history directory for `ls`. With no net external changes, it SHALL emit no change notification. Static Deep system instructions SHALL explain consolidation, numbered groups, directory discovery, and that current files are authoritative; notifications SHALL NOT repeat those instructions. File names and file contents SHALL be treated as data, not additional instructions.

#### Scenario: Large edit does not expand model input

- **GIVEN** the user pastes a large dataset into an editable text file
- **WHEN** the next turn starts
- **THEN** the notification contains only the changed-file count and path metadata within its bound
- **AND** the agent can choose to read part of the diff or the actual file

#### Scenario: More changes than fit in the notification

- **WHEN** the diff path list exceeds either notification bound
- **THEN** the notification includes the distinct source-file count, a truncated path list, and `/.deep/changes/<turn-id>/`
- **AND** ordinary directory listing reveals every remaining diff without an index file

### Requirement: Files and change history share the conversation lifecycle

File references, saved file contents, pending external changes, and published history SHALL remain bound to the same conversation across turns and runtime replicas. Published diffs SHALL be retained until the conversation's existing erasure policy removes them, subject to the existing filesystem quota model; older history SHALL NOT be silently evicted to make room. Storage/quota failures SHALL be reported explicitly rather than silently using a local copy or claiming complete history. Turn retries SHALL NOT consume another turn's pending changes or publish duplicate history. The change SHALL NOT introduce a global audit service or a new cross-replica merge guarantee.

#### Scenario: Continue on a different runtime replica

- **GIVEN** a user save completed and external changes are pending
- **WHEN** the next turn is handled by another runtime replica
- **THEN** that turn sees the saved file and publishes the pending changes
- **AND** older published diffs remain readable

#### Scenario: Conversation is erased

- **WHEN** a conversation becomes eligible for existing filesystem erasure
- **THEN** its working files, pending change data, and published diffs are removed together

### Requirement: Filesystem presentation coexists with legacy capabilities

The temporary `open_writable_document` bridge SHALL be removed without removing the existing writable-document or HTML capability used by ReAct agents. Existing document records, tables, APIs, exports, and historical UI parts SHALL remain usable. The new Deep workflow SHALL require neither legacy capability selection nor a document migration, and SHALL NOT populate legacy document content as a second live source. Existing saved configurations referencing the temporary bridge SHALL receive an explicit compatible retirement path rather than preventing access to their conversations or silently migrating their documents.

#### Scenario: Existing ReAct document remains editable

- **GIVEN** a ReAct conversation contains a writable document created before this change
- **WHEN** its owner opens, edits, and exports that document
- **THEN** the existing capability and stored document continue to work
- **AND** no filesystem migration is required

#### Scenario: Existing agent still selects the retired bridge

- **GIVEN** an existing agent configuration selects `open_writable_document`
- **WHEN** the bridge is removed from the catalog and Control Plane reconciles availability and configuration health
- **THEN** that retired selection alone does not suspend the agent or block preparation and execution
- **AND** unrelated unavailable capability IDs retain their existing validation and suspension behavior
- **AND** no callable bridge or document migration is required

#### Scenario: Deep agent needs no presentation capability

- **GIVEN** a Deep agent has no writable-document, HTML-artifact, or open-document capability selected
- **WHEN** it writes Markdown or HTML and calls `open`
- **THEN** the corresponding built-in viewer is available
- **AND** removing the bridge does not delete previously imported legacy documents
