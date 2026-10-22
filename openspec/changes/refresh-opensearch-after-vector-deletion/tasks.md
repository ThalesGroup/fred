## 1. Deletion Visibility

- [ ] 1.1 Add `refresh=true` to the `delete_by_query` params in `OpenSearchVectorStoreAdapter.delete_vectors_for_document`, keeping `conflicts=proceed`.
- [ ] 1.2 Add an offline regression test asserting the fake OpenSearch client receives both `refresh=true` and `conflicts=proceed` for a document-scoped `delete_by_query`.

## 2. Verification

- [ ] 2.1 Run the OpenSearch adapter test module and the Knowledge Flow offline unit suite (`make test`) and verify they pass.
- [ ] 2.2 Run `ruff check` and `ruff format --check` on the touched files.
- [ ] 2.3 Add the release migration note and record exact evidence in `verification.md`, stating what is not verified against a live OpenSearch.
