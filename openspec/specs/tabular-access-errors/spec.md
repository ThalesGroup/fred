# Tabular access errors Specification

## Purpose

Help tabular callers recover from invalid dataset identifiers without revealing whether inaccessible documents exist.

## Requirements

### Requirement: Actionable tabular access denials

Tabular document and dataset read denials SHALL explain that supplied identifiers can be inaccessible or invalid, that document UIDs differ from filenames and SQL aliases, and that `list_tabular_documents` returns valid `document_uid` values. The guidance MUST preserve existing authorization decisions and HTTP status mappings and MUST NOT distinguish missing from forbidden documents through new disclosures.

#### Scenario: Invalid identifier

- **WHEN** a caller submits a filename or SQL alias as a document UID and authorization denies it
- **THEN** the denial names `list_tabular_documents`, explains document UIDs, and remains HTTP 403

#### Scenario: Forbidden document

- **WHEN** authorization denies an existing document UID
- **THEN** the same denial guidance is returned without confirming existence

#### Scenario: Authorized attachment

- **WHEN** an attachment owner requests a dataset readable under existing ownership rules
- **THEN** existing attachment access remains successful
