# document-tool-reliability Specification

## Purpose

Defines how native document tools communicate exact document references and preserve controlled write failures in durable conversation history.

## Requirements

### Requirement: Document tools explain exact reference reuse

The model-facing read and summarize parameter schemas SHALL explain that document_uid is copied unchanged from a discovered document UID, distinguish filenames, titles and folder IDs, and direct discovery when no reference is available. Search SHALL explain its returned uid reference. Existing field names, accepted UID values, pagination and authorization SHALL remain unchanged; the system SHALL NOT resolve names or reconstruct altered UIDs automatically.

#### Scenario: Inspect the tool schema
- **WHEN** a provider receives the native read or summary tool schema
- **THEN** document_uid has explicit reference-source and exact-copy guidance
- **AND** the field remains an opaque string without an invented UUID restriction

#### Scenario: Reuse a discovered reference
- **WHEN** a caller supplies a discovered document UID
- **THEN** the existing document port receives that exact value and retains its existing scope enforcement

### Requirement: Invalid writable text produces a controlled failure

Writable-document tools SHALL reject NUL in title or Markdown before document storage access. The failure SHALL contain a non-empty Fred-owned diagnostic identifying the invalid field and occurrence count, with guidance to submit corrected text. It SHALL NOT mutate a document or publish a success/editor part. Valid Unicode text, tabs and line breaks SHALL remain unchanged.

#### Scenario: NUL in a create or update
- **WHEN** a writable-document tool receives NUL in its title or content
- **THEN** it returns an actionable error without accessing document storage or publishing success
- **AND** any existing document remains intact

### Requirement: Invalid text does not prevent durable failure history

History persistence SHALL represent NUL within serialized message-part and metadata string values using explicit visible notation and record the transformation count. It SHALL preserve call/result pairing, ordering, failure status and valid text without mutating live execution data. The notation SHALL be identified as diagnostic representation rather than unchanged source text.

#### Scenario: Persist a rejected write and continue
- **WHEN** a turn contains a NUL-bearing document tool call, its controlled error and subsequent response
- **THEN** a PostgreSQL history save and read preserves all those records with their original call IDs and failure status
- **AND** only the invalid historical text values are represented with the attributed notation

#### Scenario: Normal history and multiple pods
- **WHEN** normal text is persisted or another store instance reads a previously normalized turn
- **THEN** normal content is unchanged and diagnostic history remains available without process-local coordination
