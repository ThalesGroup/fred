## Why

On a pgvector deployment, `PUT /knowledge-flow/v1/document/metadata/{uid}?retrievable=false` returns success but the document stays searchable. `PgVectorStoreAdapter` does not implement `set_document_retrievable`, and `MetadataService.update_document_retrievable` saves the Postgres metadata first, then swallows the vector store's `NotImplementedError` (and any other vector failure) and reports success. Tracked by GitHub issue #3203.

## What Changes

- `PgVectorStoreAdapter.set_document_retrievable` writes `retrievable` into the JSONB metadata of every chunk of the document in its collection, in one SQL `UPDATE`, and raises on failure.
- pgvector search keeps its existing post-filter: a chunk with `retrievable=false` is never returned, a chunk without the field (legacy) stays searchable.
- `update_document_retrievable` applies the vector toggle **before** saving the metadata, off the event loop, and fails the request (HTTP 500 through the existing `MetadataUpdateError` path) when the vector state cannot be changed, including a store without toggle support. Nothing is persisted in that case.

## Capabilities

### New Capabilities

- `document-retrievability`: the retrievability toggle of an ingested document is effective in the vector index, or the request fails.

### Modified Capabilities

None.

## Impact

- Code: `core/stores/vector/pgvector_store.py`, `features/metadata/service.py` in `apps/knowledge-flow-backend`.
- API: same route, same request and success response; the OpenAPI spec is unchanged. A vector failure now yields 500 instead of a misleading 200.
- Data: pgvector documents toggled off before this fix still have `retrievable=true` (or no field) on their chunks. Operators re-apply the toggle to fix them (migration note).
- Other adapters (OpenSearch, ClickHouse, Chroma, in-memory) already implement the toggle; their behaviour is unchanged apart from failures now surfacing instead of being logged.
