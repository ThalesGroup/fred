## RENAMED Requirements

- FROM: `### Requirement: Invalid writable text produces a controlled failure`
- TO: `### Requirement: Writable tools automatically remove NUL`
- FROM: `### Requirement: Invalid text does not prevent durable failure history`
- TO: `### Requirement: NUL-bearing arguments retain durable diagnostic history`

## MODIFIED Requirements

### Requirement: Document tools explain exact reference reuse

Native vector-search model results SHALL expose each discovered reference as document_uid in both returned text and structured tool content, matching read and summary argument names, without exposing a duplicate uid key. Read/summary schemas and relevant recovery guidance SHALL explain copying that value unchanged, distinguish filenames, titles and folder IDs, and direct discovery when no reference is available. Typed citation sources, backend search contracts, accepted UID values, pagination and authorization SHALL remain unchanged; the system SHALL NOT resolve names or reconstruct altered UIDs automatically.

#### Scenario: Inspect the tool schema
- **WHEN** a provider receives the native read or summary tool schema
- **THEN** document_uid has explicit reference-source and exact-copy guidance
- **AND** the field remains an opaque string without an invented UUID restriction

#### Scenario: Reuse a discovered reference
- **WHEN** native vector search returns a document hit and the caller copies its document_uid into read or summary
- **THEN** returned text and structured content agree on document_uid and omit the old uid key
- **AND** the existing document port receives that exact value with unchanged scope enforcement
- **AND** citation sources retain their original typed UID

### Requirement: Writable tools automatically remove NUL

Writable-document tools SHALL remove U+0000 from title and Markdown before title matching and storage and SHALL save the cleaned document without a NUL-related error. The stored document and editor part SHALL contain the same cleaned text. Successful tool content SHALL disclose the affected fields and removal counts. Valid Unicode, tabs, line breaks, literal marker text and all other permitted characters SHALL remain unchanged.

#### Scenario: NUL in a create or update
- **WHEN** a writable-document tool receives NUL in title or content, including an imported Markdown file
- **THEN** it saves the cleaned values and publishes the editor part without a NUL-related failure
- **AND** it reports removal counts through both text and structured tool content

#### Scenario: Title matching and all-NUL text
- **WHEN** stripping NUL makes the title match an existing session document or leaves a supplied field empty
- **THEN** normal title matching uses the cleaned title and no additional document is created for an otherwise matching title
- **AND** an empty cleaned field does not itself cause a NUL-related tool failure

### Requirement: NUL-bearing arguments retain durable diagnostic history

History persistence SHALL represent NUL within serialized message-part and metadata string values using explicit visible notation and record the transformation count. It SHALL preserve call/result pairing, ordering, success or failure status and valid text without mutating live execution data. The notation SHALL be identified as diagnostic representation rather than unchanged source text.

#### Scenario: Persist an automatically cleaned write
- **WHEN** a turn contains original NUL-bearing write arguments, its successful cleaned save and subsequent response
- **THEN** PostgreSQL history save/read preserves those records with their original call IDs and success status
- **AND** raw historical argument values use attributed notation while saved document content contains no inserted marker

#### Scenario: Persist a rejected write and continue
- **WHEN** a legacy turn containing a rejected NUL-bearing write is persisted or read
- **THEN** the original call/result pairing and failure status remain available
- **AND** its diagnostic history is not rewritten as a successful save

#### Scenario: Normal history and multiple pods
- **WHEN** normal text is persisted or another store instance reads a previously normalized turn
- **THEN** normal content is unchanged and diagnostic history remains available without process-local coordination
