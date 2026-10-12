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
