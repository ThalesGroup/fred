## Purpose

Defines when a document's vectors stop being visible to search and counting after the vector store reports their deletion.

## ADDED Requirements

### Requirement: Deleted document vectors are not visible after deletion returns
When the OpenSearch vector store's document-scoped vector deletion returns successfully, the deleted chunks SHALL NOT be returned by any subsequent search or counted by any subsequent chunk count for that document.

#### Scenario: Immediate count after deletion
- **GIVEN** a document whose chunks are indexed in OpenSearch
- **WHEN** its vectors are deleted and its chunk count is read immediately afterwards
- **THEN** the count is zero, without waiting for the index's periodic refresh

#### Scenario: Immediate search after deletion
- **GIVEN** a document whose chunks match a query
- **WHEN** its vectors are deleted and the same query runs immediately afterwards
- **THEN** none of that document's chunks are returned

### Requirement: Repeated deletion of the same document stays benign
The document-scoped vector deletion MUST tolerate a concurrent or repeated purge of the same document without failing on version conflicts.

#### Scenario: Two purges of a cancelled ingestion
- **WHEN** the indexing thread and the workflow compensation both delete the same document's vectors
- **THEN** both calls complete without a conflict error and no chunk of that document remains visible
