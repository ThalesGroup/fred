## Context

`retrievable` lives in two places: `metadata.source.retrievable` (Postgres metadata, shown in the UI) and a per-chunk copy in the vector index, which is what search filters on (`metadata_terms={"retrievable": [True]}` in `VectorSearchService`). pgvector stores chunk metadata as JSONB in `langchain_pg_embedding.cmetadata`, scoped by `langchain_pg_collection.name`; the adapter already updates it in place for renames (`set_document_name`, `jsonb_set`).

## Decisions

### One JSONB update per document

`set_document_retrievable` runs one `UPDATE langchain_pg_embedding ... SET cmetadata = jsonb_set(cmetadata, '{retrievable}', to_jsonb(CAST(:value AS boolean)))` joined to the collection and filtered on `cmetadata ->> 'document_uid'`, the same shape as `set_document_name` and `delete_vectors_for_document`. `jsonb_set` creates the key when missing, so legacy chunks get it too. Unlike `set_document_name` it raises `RuntimeError` on failure (as OpenSearch and ClickHouse do), so the caller can refuse the toggle.

### Search filter stays a post-filter

`ann_search` already drops `retrievable` from the SQL push-down and applies `_matches_metadata_terms` to the candidates, treating a missing field as retrievable — the same semantics as OpenSearch and the in-memory store. No filter change is needed: the bug was only that the chunks were never updated. Pushing `retrievable` into SQL was rejected for this slice: the LangChain filter DSL has no "missing or true" operator that works on both `langchain_postgres` and the legacy `langchain_community` store without restructuring every pushed-down filter.

Known limit (unchanged by this slice): post-filtering runs on `4 * k` candidates (capped at 200), so a disabled document whose chunks dominate the nearest neighbours can reduce the number of hits returned. It never leaks a disabled chunk.

### Vector first, then metadata — no rollback

The service applies the vector toggle before saving the metadata. If the vector update fails, or the store does not support it, the request fails and nothing was written. If the metadata save fails after the vector update, the request fails too; the toggle is idempotent, so a retry converges. This avoids compensating writes (a rollback that can itself fail) and keeps the change to a reordering. The vector call goes through `asyncio.to_thread`, like rename and delete already do, because every store client is synchronous.

A document not yet `VECTORIZED` has no chunks to update; only the metadata is saved, as before.

## Non-Goals

- Pushing the `retrievable` filter into pgvector SQL (see above).
- Fixing `_create_store`, which passes `connection_string` to `langchain_postgres.PGVector` (whose parameter is `connection`) and therefore always falls back to the legacy store.
- Changing rename's best-effort vector sync.
- A bulk repair job for documents toggled before the fix: re-applying the toggle is enough (migration note).
