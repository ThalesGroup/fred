## Purpose

Defines how the platform corpus audit classifies vector-store data that has no corpus metadata row.

## ADDED Requirements

### Requirement: Session attachments are not corpus orphans
The corpus audit SHALL NOT report a vector-store document UID without a metadata row as `orphan_vectors` when the vector store classifies that UID as a session-scoped attachment.

#### Scenario: Session attachment beside a genuine corpus orphan
- **GIVEN** two vector-store UIDs without metadata rows, one whose chunks all carry the session-scope marker and one whose chunks do not
- **WHEN** a platform administrator runs the corpus audit
- **THEN** only the UID without the session-scope marker is reported, with `orphan_vectors`

#### Scenario: Metadata-backed documents are not classified
- **WHEN** the corpus audit evaluates a UID that has a metadata row
- **THEN** it does not query session-scope classification for that UID

### Requirement: Classification failure keeps the orphan visible
The corpus audit MUST keep reporting a vector-only UID as `orphan_vectors` whenever session-scope classification cannot positively confirm a session attachment.

#### Scenario: Adapter cannot classify
- **GIVEN** a vector store that does not support fetching a document's chunks
- **WHEN** the corpus audit evaluates a vector-only UID
- **THEN** the UID is reported with `orphan_vectors`

#### Scenario: Classification lookup fails
- **GIVEN** a vector store whose chunk lookup raises an error for a vector-only UID
- **WHEN** the corpus audit evaluates that UID
- **THEN** the UID is reported with `orphan_vectors` and the failure is logged
