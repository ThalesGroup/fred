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

When the corpus tree reports truncation, `list_document_tree` SHALL include an explicit incomplete-listing notice in both model-facing carriers. Its description SHALL state that a partial tree cannot establish the latest arrival across the entire requested scope. Metadata rendering SHALL retain the existing tree character budget and whole-line pruning behavior.

#### Scenario: Added metadata makes a tree exceed its budget

- **WHEN** a rendered tree exceeds the requested character budget
- **THEN** the returned tree stays within that budget and prunes whole branches or items
- **AND** the agent receives an explicit incomplete-listing notice
- **AND** its instructions warn against a scope-wide latest-document conclusion from that partial listing

### Requirement: Document tree tool details are compact and expandable

The tool detail panel SHALL group documents by folder and show compact rows containing document name, format and Fred arrival date/time. Expanding a row SHALL reveal its remaining metadata, with at most one document expanded per tool result. Missing optional descriptive fields SHALL be omitted, missing dates SHALL be explicit, and internal document/folder identifiers SHALL NOT be displayed. Unsupported or malformed records SHALL NOT cause raw internal data to be displayed.

#### Scenario: Expand one document

- **GIVEN** a tree result containing multiple documents with the agreed metadata
- **WHEN** the user expands one document
- **THEN** its remaining labeled metadata is visible
- **AND** the other documents remain compact
- **WHEN** the user expands another document
- **THEN** the previously expanded document is collapsed

#### Scenario: Identify the latest displayed arrival

- **GIVEN** multiple displayed documents with known arrival timestamps
- **WHEN** the tool detail is rendered
- **THEN** the latest known instant among displayed documents is identified as the most recent displayed arrival
- **AND** a truncated result retains its incomplete-listing warning
- **AND** displayed counts refer to unique displayed documents rather than a corpus total

#### Scenario: Read a historical tool result

- **GIVEN** a historical plain text tree with uploaded-date leaves
- **WHEN** the user opens the tool detail
- **THEN** the tree remains readable without internal ids
- **AND** the historical uploaded date is not reinterpreted as an authoritative Fred arrival date

#### Scenario: Names and metadata contain punctuation

- **GIVEN** document names or metadata containing brackets, slashes or newlines
- **WHEN** the current tree result is parsed and displayed
- **THEN** those values remain document data rather than extra folder/document records
- **AND** the metadata is displayed as text
