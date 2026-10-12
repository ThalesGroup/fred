## MODIFIED Requirements

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
