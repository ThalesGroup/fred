## 1. pgvector toggle

- [x] 1.1 Implement `PgVectorStoreAdapter.set_document_retrievable` as one JSONB update scoped to the collection and document, raising on failure.
- [x] 1.2 Add an offline adapter test: off/on round trip on the document's chunks only, and `ann_search` hiding the document while off.
- [x] 1.3 Add an `integration_postgres` test that toggles and searches against a real pgvector database (skipped when the `vector` extension is unavailable).

## 2. Service

- [x] 2.1 Apply the vector toggle before saving the metadata, through `asyncio.to_thread`, and let any failure (including `NotImplementedError`) fail the request.
- [x] 2.2 Add service tests: a failing or unsupported store leaves the metadata unchanged and raises; a non-vectorized document does not call the store.

## 3. Close-out

- [x] 3.1 Add the migration note for documents toggled off before the fix.
- [x] 3.2 Run focused tests, the Knowledge Flow offline suite and ruff; record evidence in `verification.md`.
- [x] 3.3 Review the diff for event-loop blocking and search-path cost.
