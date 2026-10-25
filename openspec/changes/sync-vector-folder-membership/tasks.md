## 1. Vector store operation

- [x] 1.1 Add the required `set_document_tag_ids` to `BaseVectorStore`
- [x] 1.2 Implement it for OpenSearch (`update_by_query`, raise on reported failures), pgvector (one `jsonb_set` update), ClickHouse (one mutation of the `tag_ids` column), Chroma and in-memory; failures raise
- [x] 1.3 Make Chroma's folder filter match one id inside a multi-folder list

## 2. Membership changes

- [x] 2.1 Link and unlink write the new ids to the vector store (off the event loop) before saving the metadata row, for vectorized documents only
- [x] 2.2 A vector failure raises `MetadataUpdateError` and leaves the row, storage charge and ReBAC relation unchanged

## 3. Verification

- [x] 3.1 Offline service tests: link and unlink after ingestion, failure on link and unlink, non-vectorized document
- [x] 3.2 Offline adapter tests: OpenSearch, pgvector, ClickHouse with fake clients; Chroma and in-memory end to end through `ann_search`
- [x] 3.3 Offline refile test through library sync
- [x] 3.4 Full offline Knowledge Flow suite and ruff on touched files; performance review of the diff
- [x] 3.5 Migration note (impact `minor`, remediation for documents linked before the fix)
- [ ] 3.6 Live OpenSearch link/unlink and end-to-end pgvector search (developer; pgvector chunk update verified live, see verification.md)
