# team-resource-spaces Specification

## Purpose

Defines the current Team Resources surface and the boundary between corpus documents and technical agent files.

## Requirements

### Requirement: Team Resources exposes the corpus

The Team Resources page SHALL expose the searchable team corpus. It SHALL NOT expose general-purpose personal, team-shared, or agent-files roots.

#### Scenario: Open Team Resources

- **WHEN** a user opens Team Resources for a team
- **THEN** the corpus workspace is available without personal, team-shared, or agent-files tabs

### Requirement: Retired general-purpose areas are unavailable

The Knowledge Flow filesystem API SHALL reject the retired `/teams/{team_id}/users` and `/teams/{team_id}/shared` areas before accessing storage. Retirement SHALL NOT delete previously stored objects in those areas.

#### Scenario: Request a retired area

- **WHEN** a caller lists, reads, or mutates a path in either retired area
- **THEN** the request is rejected without reading or changing stored objects

### Requirement: Technical agent files remain available

Knowledge Flow SHALL retain authenticated binary upload, download, and delete operations for agent configuration assets and generated outputs under `/teams/{team_id}/agents/{agent_instance_id}/`. PPT Filler SHALL continue to load its per-instance template and publish downloadable presentations through these paths.

#### Scenario: Fill a presentation

- **GIVEN** an agent instance has a stored PPT Filler template
- **WHEN** the capability produces a presentation for a conversation
- **THEN** the template can be read and the generated presentation can be downloaded through the retained technical storage path

### Requirement: Corpus access remains separate

The corpus and conversation attachments SHALL continue to use their existing ingestion, metadata, search, and download APIs. The `/corpus` virtual filesystem view SHALL remain read-only, and `list_document_tree` SHALL continue to list authorized indexed documents.

#### Scenario: Agent lists corpus documents

- **WHEN** an authorized agent invokes `list_document_tree`
- **THEN** it receives the indexed documents permitted by the document-access contract

### Requirement: Corpus tree exposes distinct document timestamps

Each authorized document leaf returned by `list_document_tree` SHALL expose explicitly labeled `added_to_kb`, `created`, and `modified` dates from the stored document metadata. Known dates SHALL include time, timezone, and available subsecond precision in ISO 8601. Unavailable dates SHALL be shown as unknown, without substitution. Arrival in Fred SHALL use `source.date_added_to_kb`; the tool description SHALL distinguish arrival from file creation, metadata modification, and ingestion completion. Temporal metadata SHALL be available in both ReAct text content and Graph text blocks. Available title, format/MIME, language, page/row counts, business labels and source SHALL also be exposed on each authorized leaf.

#### Scenario: Embedded creation and Fred arrival have opposite order

- **GIVEN** two authorized documents whose embedded creation dates and arrival dates have opposite ordering
- **WHEN** the agent lists their containing folder
- **THEN** both dates are labeled separately for each document
- **AND** the description identifies `added_to_kb` as the date to compare for latest arrival

#### Scenario: Multiple arrivals on one day

- **GIVEN** two authorized documents arrived on the same date at different times
- **WHEN** their leaves are rendered
- **THEN** their timestamps preserve time, timezone, and available subsecond precision

#### Scenario: Embedded dates are unavailable

- **GIVEN** an authorized document has a stored arrival timestamp and no creation or modification timestamp
- **WHEN** the agent lists it
- **THEN** its arrival timestamp is visible and its other dates are explicitly unknown

#### Scenario: Scope excludes a document

- **GIVEN** a document is unauthorized or excluded by the effective listing scope
- **WHEN** the agent lists corpus documents
- **THEN** neither its leaf nor its temporal metadata is exposed

#### Scenario: Both agent execution models receive metadata

- **WHEN** a ReAct or Graph agent invokes `list_document_tree`
- **THEN** its model-facing text contains the same temporal metadata for returned leaves

### Requirement: Partial corpus trees do not imply complete chronology

The corpus tree SHALL use a default character budget of 20,000 and accept up to 60,000 characters across its existing tool, SDK, runtime and HTTP boundaries. Whole-branch/item pruning SHALL remain available beyond that budget. When truncation occurs, the tool SHALL retain explicit model-facing incomplete-listing information in both carriers and its description SHALL prohibit a scope-wide latest-arrival claim from a partial tree. The UI SHALL use only a discreet localized Truncated footer.

#### Scenario: Added metadata makes a tree exceed its budget

- **WHEN** a rendered tree exceeds the requested character budget
- **THEN** it stays within that budget by pruning whole branches or items
- **AND** both model-facing carriers indicate incompleteness
- **AND** the UI shows its localized Truncated marker at the end without a warning block

#### Scenario: Metadata-rich listings fit the raised default

- **GIVEN** an authorized tree larger than 6,000 but smaller than 20,000 characters
- **WHEN** the tree tool is invoked with no explicit max_chars
- **THEN** all its scoped leaves are returned without truncation

### Requirement: Document tree tool details are compact and expandable

The tool detail panel SHALL present nested collapsible folders and compact document rows with a file icon and a focusable name. Folder and document names SHALL use the shared monospace typography. The rows SHALL NOT display dates or expand metadata inline. Hovering or keyboard-focusing the document SHALL reveal labeled metadata in a viewport-bounded tooltip; touch users SHALL be able to access it as well. Escape SHALL dismiss the metadata tooltip without closing the tool drawer. File creation, modification and format SHALL NOT be displayed in the metadata tooltip. Missing optional descriptive fields SHALL be omitted, missing dates SHALL be explicit, and internal document/folder identifiers SHALL NOT be displayed. Arrival labels SHALL use the configured primary deployment display name. Unsupported or malformed records SHALL NOT expose raw internal data.

#### Scenario: Expand one document

- **GIVEN** a tree result containing nested folders and documents
- **WHEN** the user opens the tool detail
- **THEN** folders retain their nesting and the file rows contain no dates
- **WHEN** the user hovers or keyboard-focuses a document
- **THEN** its labeled metadata is visible without changing the tree layout
- **AND** Escape dismisses the tooltip while leaving the tool drawer open

#### Scenario: Consult metadata on a narrow touch viewport

- **WHEN** a touch user activates a document on a narrow viewport
- **THEN** its metadata is available without clipping or horizontal page overflow

#### Scenario: Identify the latest displayed arrival

- **GIVEN** displayed documents with known arrival timestamps
- **WHEN** the user consults the latest displayed document's metadata
- **THEN** it is identified as the most recent displayed arrival
- **AND** a truncated result has only a discreet localized Truncated marker at the bottom of the tree, without an alarming warning block
- **AND** counts refer to unique displayed documents rather than a corpus total

#### Scenario: Read a historical tool result

- **GIVEN** a historical plain text tree with uploaded-date leaves
- **WHEN** the user opens the tool detail and its metadata tooltip
- **THEN** the tree remains readable without internal ids
- **AND** the historical uploaded date is not reinterpreted as an authoritative arrival date

#### Scenario: Names and metadata contain punctuation

- **GIVEN** document names or metadata containing brackets, slashes or newlines
- **WHEN** the current tree result is parsed and displayed
- **THEN** those values remain document data rather than extra folder/document records
- **AND** metadata is displayed as text

### Requirement: Corpus search respects current contextual membership

Corpus search SHALL return only documents authorized for the caller and currently belonging to the requested ownership context. Explicit document selection SHALL NOT bypass that context. Library and document selections SHALL form a union within that context; a document-only selection SHALL NOT enable a whole-library search. These guarantees SHALL hold for semantic, strict and hybrid search.

#### Scenario: Multi-team user names a document from another team

- **GIVEN** a user belongs to teams A and B and a document belongs only to B
- **WHEN** the user searches in team A with that document ID, alone or alongside an A library
- **THEN** no content or source metadata from the B document is returned
- **AND** an authorized selected A document remains searchable

#### Scenario: Mixed and document-only selections retain their meaning

- **GIVEN** two authorized libraries and several documents inside the same team
- **WHEN** a user selects one library and a document in the other
- **THEN** eligible results can come from either selected source
- **WHEN** the user selects only that document
- **THEN** other corpus documents are excluded

### Requirement: Stale index membership cannot authorize corpus search hits

Corpus search SHALL validate candidate documents against current canonical membership and the caller's applicable read authorization before exposing their content or source metadata. Missing canonical metadata SHALL exclude the candidate. An unavailable authorization authority SHALL fail the search rather than permit unchecked results.

#### Scenario: Shared document is removed from the selected library

- **GIVEN** a document belonged to libraries A and B and now belongs only to B
- **AND** the search index still records both libraries
- **WHEN** a user searches only library A
- **THEN** no content or source metadata from that document is returned
- **AND** this remains true even if an obsolete read grant survives
- **WHEN** an authorized B reader searches B
- **THEN** the document remains searchable

#### Scenario: Candidate metadata is absent or permission is denied

- **WHEN** the index returns a corpus candidate whose canonical metadata is absent or whose read permission is denied
- **THEN** the candidate is excluded while other eligible candidates remain available

#### Scenario: Authorization cannot be established

- **WHEN** authorization fails because the authority is unavailable
- **THEN** the request fails without returning unchecked corpus hits

### Requirement: Corpus selection preserves enabled conversation attachments

Enabled attachment search SHALL remain scoped to the authenticated user and current session independently of corpus library or document selection. Search SHALL use the current indexed sources on each turn and preserve configured source ceilings.

#### Scenario: Late attachment with a selected corpus document

- **GIVEN** a conversation has already completed a turn
- **AND** a new attachment has completed ingestion and indexing for that user and session
- **WHEN** another turn searches with an authorized corpus document selected and attachments enabled
- **THEN** the attachment remains eligible alongside that corpus document
- **AND** another user or session cannot retrieve the attachment

#### Scenario: Late library document in the same conversation

- **GIVEN** a conversation has already completed a turn using a selected library
- **WHEN** another document finishes indexing in that library and the conversation searches again
- **THEN** that document is eligible without recreating the conversation

#### Scenario: Attachments are disabled

- **WHEN** attachment search is disabled for the request
- **THEN** selecting corpus documents does not enable attachment retrieval

### Requirement: Known folder documents are authorized independently of global inventory size

Explicit document reads and single/multiple-folder document inventories SHALL evaluate the existing document permissions for their stored candidates without relying on a complete global list of readable documents. Paginated browsing SHALL retain its current ordering, offsets, limits and stored-total semantics. Authorization work SHALL depend on the selected candidates and use bounded concurrency.

#### Scenario: Small folder within a large readable corpus

- **GIVEN** a user can read more than 1,000 documents and a selected folder contains 20 readable documents
- **WHEN** the user lists that folder or requests a page covering its 20 documents
- **THEN** all 20 documents are returned regardless of which objects a global authorization inventory would include
- **AND** documents elsewhere do not add document checks to that request

#### Scenario: Shared document in several selected folders

- **GIVEN** one document belongs to two selected folders
- **WHEN** their document inventories are resolved together
- **THEN** its READ decision is evaluated once within that candidate batch
- **AND** its membership in both folders is preserved

#### Scenario: A stored candidate is unreadable

- **WHEN** the user's document READ permission is denied for a stored listing candidate
- **THEN** that document is excluded without widening the user's access

#### Scenario: Authorization cannot be evaluated

- **WHEN** authorization of a known candidate fails because the authority is unavailable
- **THEN** the request fails explicitly instead of interpreting the failure as an empty readable inventory

### Requirement: Folder deletion does not treat unreadable or unresolved contents as absent

Document-folder deletion SHALL use canonical stored subtree and document membership. It SHALL retain existing folder and document permission checks, refuse denied or unresolved contents before mutation, and refuse final folder removal while known document links remain. Subtrees SHALL remain bounded by owner, type and path boundaries. This requirement does not guarantee atomicity with concurrent ingestion or repair partial external-store cleanup failures.

#### Scenario: Delete a populated folder above the authorization inventory cap

- **GIVEN** a readable corpus larger than 1,000 documents, an authorized folder containing 20 documents, no concurrent writers and healthy stores
- **WHEN** the user deletes that folder
- **THEN** every stored document membership is processed before the folder is removed
- **AND** last-membership documents, their vectors and content are removed through the existing deletion path and quota is released once

#### Scenario: One candidate cannot be processed

- **GIVEN** the canonical folder inventory contains a document whose READ authorization is denied or fails
- **WHEN** the user requests folder deletion
- **THEN** the request fails before mutating the subtree rather than omitting that document

#### Scenario: Membership remains after removal attempts

- **WHEN** processing returns but a canonical document link to the folder still exists
- **THEN** the folder is retained and the operation reports failure

#### Scenario: Document also belongs outside the deleted subtree

- **GIVEN** a document belongs to the deleted subtree and another surviving folder
- **WHEN** the subtree is deleted
- **THEN** only its subtree memberships are removed
- **AND** the document, content, vectors and surviving access remain available

#### Scenario: Same folder path under another owner

- **GIVEN** two owners have folders with the same path
- **WHEN** one owner's subtree is deleted
- **THEN** the other owner's folders and documents are unchanged

### Requirement: Team Resources rows support selection and native name copying

The Team Resources corpus table SHALL use row highlighting and its checkbox state to show selected folders and documents. A plain click on a row, including its name, SHALL select that row alone; Ctrl/Cmd-click SHALL toggle that row within the current selection. Checkboxes SHALL continue to toggle independently. Dragging over a folder or document name SHALL allow native text selection and copying without changing row selection. Clicking or double-clicking SHALL not highlight name text.

#### Scenario: Select one row by its name

- **WHEN** a user clicks a folder or document name once without a modifier
- **THEN** only that row is selected and highlighted
- **AND** its name text is not highlighted by the click
- **AND** the name uses the same pointer cursor as the row

#### Scenario: Select several rows

- **GIVEN** one folder or document row is selected
- **WHEN** the user Ctrl/Cmd-clicks another row
- **THEN** both rows are selected and available to the existing bulk actions
- **WHEN** the user Ctrl/Cmd-clicks a selected row
- **THEN** that row is removed from the selection

#### Scenario: Copy a name

- **WHEN** the user starts dragging in the name cell, including its empty space to the right, and moves across a folder or document name
- **THEN** the exact name text range can be selected and copied with the browser's native command
- **AND** the selected rows do not change when the drag ends

#### Scenario: Clear copied name text by clicking away

- **GIVEN** the user selected folder or document name text by dragging
- **WHEN** the user clicks elsewhere within the page, including below the last table row
- **THEN** the text highlight clears
- **AND** checked row selection remains unchanged

#### Scenario: Use an embedded control

- **WHEN** the user activates a row checkbox, preview action or menu action
- **THEN** that control performs its existing action without a second row selection change

#### Scenario: Open row actions with right-click

- **WHEN** the user right-clicks a folder or document row
- **THEN** the same available actions as the row's three-dot button open beside the pointer
- **AND** the three-dot button remains available
- **AND** the checked row selection does not change
- **WHEN** the user right-clicks name text already selected by dragging
- **THEN** the browser's native copy menu remains available

### Requirement: Team Resources rows open on double-click

The Team Resources corpus table SHALL open a folder on double-click anywhere on its row, including its name, and SHALL open a document's existing preview on double-click anywhere on its row. A single click SHALL only select the row. Keyboard users SHALL retain a way to open folders and document previews.

#### Scenario: Open a folder

- **WHEN** a user double-clicks a folder row or its name
- **THEN** the workspace navigates into that folder
- **AND** the double-click does not highlight its name text

#### Scenario: Preview a document

- **WHEN** a user double-clicks a document row or its name
- **THEN** the existing document preview opens
- **AND** the double-click does not highlight its name text

#### Scenario: Single-click a resource

- **WHEN** a user clicks a folder or document row once
- **THEN** the workspace does not navigate and no preview opens

#### Scenario: Open with the keyboard

- **WHEN** a keyboard user activates the focused folder name with Enter or Space, or uses the existing document preview control
- **THEN** the folder or document preview opens

### Requirement: Team Resources reveals complete table values

The Team Resources corpus table SHALL reveal the complete displayed value of a document or folder name, size, creation date, or uploader when a pointer hovers its text. Disclosure SHALL leave row selection, native name copying, sorting, and row actions unchanged.

#### Scenario: Inspect a long document name

- **GIVEN** a document name is visually truncated in the table
- **WHEN** the user hovers the name
- **THEN** the complete displayed name is readable without widening the column

#### Scenario: Inspect folder and metadata cells

- **WHEN** the user hovers a folder name or a size, creation date, or uploader value
- **THEN** the complete displayed value is readable, including when the cell is visually truncated
- **AND** clicking or dragging the row retains its existing behavior

### Requirement: Team Resources table columns can be resized

The Team Resources corpus table SHALL let users adjust the width of each labeled data column by dragging with a pointer. Header and body columns SHALL remain aligned during and after resizing; horizontal and vertical scrolling, sorting, selection, and row actions SHALL remain usable. Other tables SHALL retain their existing width behavior unless they enable resizing.

#### Scenario: Drag a column boundary

- **WHEN** the user drags a labeled column's resize control
- **THEN** that column changes width within usable bounds and its header stays aligned with its cells
- **AND** the table can scroll horizontally if its columns no longer fit

#### Scenario: Use a table without resize enabled

- **WHEN** another table renders without requesting column resizing
- **THEN** it has no resize controls and retains its existing column widths and interactions

### Requirement: Team Resources supports bounded range selection

The Team Resources corpus table SHALL let a person Shift-click a row or its checkbox to select the inclusive range from the last selected row within the currently rendered page. Files and folders in that range SHALL be selected. A page change or cleared selection SHALL reset the anchor. A Shift-click without an available anchor SHALL select only the clicked row. Ctrl/Cmd-click, ordinary click, text dragging, and row actions SHALL retain their existing behavior.

#### Scenario: Select a range on one page

- **GIVEN** a person has selected a row on the current page
- **WHEN** they Shift-click another row or its checkbox on that page
- **THEN** the contiguous visible rows between those endpoints, including folders, are selected

#### Scenario: Change pages before Shift-click

- **GIVEN** a person selected a row on one page
- **WHEN** they change pages and Shift-click a row
- **THEN** only the clicked row is selected on the new page

### Requirement: Team Resources provides a persistent resource tree

The Team Resources corpus workspace SHALL offer an in-scope folder tree beside the main table. The tree SHALL start closed by default, use a compact table-toolbar opener rather than a full-height collapsed rail, and restore the person's saved open/closed choice across visits and devices. It SHALL remain resizable with browser-local width, compact indentation, horizontally scrollable paths, table-sized text, and a full-row current-folder highlight including on hover.

#### Scenario: Resize and collapse the tree

- **WHEN** the user activates the close control in the tree header
- **THEN** a compact file-browser control remains in the table toolbar and the table gains the released width without a vertical launcher rail
- **WHEN** the user activates that control
- **THEN** the tree reopens at its previous browser-local width
- **WHEN** the user drags the tree's edge
- **THEN** its width changes within the page's bounds and the table remains usable

#### Scenario: Default closed and restore the person's choice

- **GIVEN** a person has no saved file-browser choice
- **WHEN** they open a corpus workspace
- **THEN** the tree is closed
- **WHEN** they open the tree and later visit a corpus workspace on another device
- **THEN** the tree is open for that person

#### Scenario: Show a deeply nested path

- **WHEN** a nested path or long name exceeds the tree width
- **THEN** the user can scroll horizontally to see the full item
- **WHEN** the user points at the current folder
- **THEN** its entire row remains highlighted

### Requirement: Resource tree follows file browser interactions

A single click on a tree folder SHALL navigate the main table to it without expanding it. Double-clicking the folder or clicking its chevron SHALL expand or collapse its nested children in place. Double-clicking a file SHALL open the existing document preview. Tree navigation SHALL preserve the table's checkbox selection except for the table's existing behavior when changing folders.

#### Scenario: Browse a nested folder

- **WHEN** the user clicks a nested folder once
- **THEN** the main table navigates to that folder and the tree reveals its ancestor path
- **WHEN** the user double-clicks the folder or clicks its chevron
- **THEN** its nested children expand or collapse without navigating again

#### Scenario: Preview a file

- **GIVEN** a file appears under an expanded folder
- **WHEN** the user double-clicks the file
- **THEN** the existing document preview opens for that file

### Requirement: Resource tree reuses file and folder actions

Right-clicking a tree folder or file SHALL offer the actions available from its table row under the same permission and state rules. Dragging OS files over a tree folder SHALL highlight only the pointed drop target, and dropping them SHALL use the existing import flow for that folder.

#### Scenario: Use a context action

- **WHEN** the user right-clicks a folder or file in the tree
- **THEN** the available actions match those of its table row
- **WHEN** the user closes the context menu with Escape
- **THEN** focus returns to the tree item that opened it

#### Scenario: Drop files on a folder

- **WHEN** the user drags OS files over a tree folder
- **THEN** that folder alone shows the drop highlight
- **WHEN** the user drops the files
- **THEN** the existing import flow targets that folder

### Requirement: Resource tree bounds file loading

Expanded folders SHALL load their direct files in bounded pages with a load-more action. A collapsed tree SHALL not initiate folder file loads.

#### Scenario: Open a large folder

- **GIVEN** a folder contains more files than one tree page
- **WHEN** the user expands it
- **THEN** the tree loads only the first page and offers an action to load more

#### Scenario: Refresh while the tree is collapsed

- **WHEN** the resource tags refresh while the tree is collapsed
- **THEN** no tree file loads start until the tree is reopened
