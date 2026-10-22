## 1. Vector store operation

- [ ] 1.1 Add the required `set_document_tag_ids` to `BaseVectorStore`
- [ ] 1.2 Implement it for OpenSearch (`update_by_query`, raise on reported failures), pgvector (one `jsonb_set` update), ClickHouse (one mutation of the `tag_ids` column), Chroma and in-memory; failures raise
- [ ] 1.3 Make Chroma's folder filter match one id inside a multi-folder list

## 2. Membership changes

- [ ] 2.1 Link and unlink write the new ids to the vector store (off the event loop) before saving the metadata row, for vectorized documents only
- [ ] 2.2 A vector failure raises `MetadataUpdateError` and leaves the row, storage charge and ReBAC relation unchanged

## 3. Verification

- [ ] 3.1 Offline service tests: link and unlink after ingestion, failure on link and unlink, non-vectorized document
- [ ] 3.2 Offline adapter tests: OpenSearch, pgvector, ClickHouse with fake clients; Chroma and in-memory end to end through `ann_search`
- [ ] 3.3 Offline refile test through library sync
- [ ] 3.4 `make test` and ruff in `apps/knowledge-flow-backend`; performance review of the diff
- [ ] 3.5 Migration note (impact `minor`, remediation for documents linked before the fix)
- [ ] 3.6 Live pgvector and OpenSearch link/unlink check (developer, k3d or local stack)
