## Purpose

Defines how Knowledge Flow applies a document's retrievability toggle to its indexed chunks so search honours it on every supported vector store.

## ADDED Requirements

### Requirement: The retrievability toggle updates every indexed chunk
When a user toggles the `retrievable` flag of a vectorized document, Knowledge Flow SHALL set that value on every chunk of the document in the configured vector store, without deleting or re-embedding the chunks. This SHALL hold for the pgvector store as for OpenSearch, ClickHouse, Chroma and the in-memory store.

#### Scenario: Toggle off then on in pgvector
- **WHEN** a vectorized document stored in pgvector is toggled to `retrievable=false` and then back to `retrievable=true`
- **THEN** every chunk of that document carries `retrievable=false` after the first toggle and `retrievable=true` after the second, and chunks of other documents are unchanged

### Requirement: Search never returns a non-retrievable chunk
Vector search SHALL exclude chunks whose `retrievable` value is `false`, and SHALL keep returning chunks that have no `retrievable` value.

#### Scenario: Disabled document is hidden from pgvector search
- **WHEN** a document stored in pgvector is toggled to `retrievable=false` and a search matches its content
- **THEN** none of its chunks is returned, and the document is returned again once toggled back to `retrievable=true`

#### Scenario: Legacy chunk without the field
- **WHEN** a chunk was indexed without a `retrievable` value
- **THEN** search treats it as retrievable

### Requirement: A toggle that cannot reach the vector index fails
Knowledge Flow MUST NOT report a successful retrievability toggle for a vectorized document when the vector store could not apply it. In that case the request SHALL fail with a server error and the document metadata SHALL keep its previous `retrievable` value.

#### Scenario: Vector store rejects the toggle
- **WHEN** a user toggles a vectorized document and the vector store raises an error or does not support the toggle
- **THEN** the request fails and the stored metadata still holds the previous `retrievable` value

#### Scenario: Document not vectorized
- **WHEN** a user toggles a document that has not been vectorized
- **THEN** the metadata is updated and the vector store is not called
