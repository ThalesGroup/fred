## Why

After a document is deleted, its OpenSearch chunks can stay searchable, countable and visible to the corpus audit until the index's next periodic refresh (about one second locally). `delete_vectors_for_document` issues `delete_by_query` without a refresh, while the sibling per-document writes (`set_document_retrievable`, `set_document_name`) already refresh. Immediate post-delete checks therefore report stale chunks. Tracked by GitHub issue #3202.

## What Changes

- `OpenSearchVectorStoreAdapter.delete_vectors_for_document` requests `refresh=true` on its `delete_by_query`, alongside the existing `conflicts=proceed`, matching the per-document update paths.
- An offline regression test asserts the OpenSearch client receives both options.

## Capabilities

### New Capabilities

- `document-vector-deletion`: Defines when a document's vectors stop being visible to search and counting after the vector store reports their deletion.

### Modified Capabilities

None.

## Impact

- Affected code: `apps/knowledge-flow-backend/knowledge_flow_backend/core/stores/vector/opensearch_vector_store.py` and its adapter test module.
- Affected flows: document deletion, tag-removal purge, re-vectorization and cancelled-ingestion cleanup — every caller of `delete_vectors_for_document` on the OpenSearch backend.
- Other vector stores are unchanged: pgvector deletes transactionally; other adapters keep their own visibility semantics.
- No API, configuration, schema or stored-data change.
