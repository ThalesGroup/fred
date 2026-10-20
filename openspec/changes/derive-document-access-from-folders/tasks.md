## 1. Visible truncation for remaining enumerations

- [x] 1.1 `OpenFgaRebacEngine._lookup_resources_raw` keeps plain `list_objects` and warns at 1,000 results or 2.5 s
- [x] 1.2 Tests: warning at the result limit, near the deadline, and none below both

## 2. Readable documents from authorized folders

- [x] 2.1 Tabular `_resolve_authorized_datasets` builds candidates from scope tags (or readable tags when unscoped); the service-agent branch folds in
- [x] 2.2 `MetadataService.get_documents_metadata` and the three label methods use readable tags
- [x] 2.3 Label store methods narrow by `tag_ids` instead of `document_uids`
- [x] 2.4 `ResourceService.list_resources_by_kind` filters by readable tags

## 3. Verification

- [x] 3.1 Offline: tabular list/describe/query/search with 1,500 and 3,000 readable documents, target outside the first 1,000, and a fake that fails on any document enumeration
- [x] 3.2 Offline: labels over a 1,500-document folder, document and resource listings narrowed by readable folders
- [ ] 3.3 Validation scenario: 3,000-document corpus with a tabular target (run by the developer on k3d)
- [x] 3.4 Migration note, impact none, truncation-warning guidance
- [ ] 3.5 Record k3d evidence; archive once complete

## Verification evidence

- fred-core offline: 1,279 passed, 1 skipped, 42 deselected; `make code-quality` clean.
- Knowledge Flow offline: 1,560 passed, 2 skipped, 45 deselected; `make code-quality` clean.
- The 1,500/3,000 tabular test fails on the previous resolver (document enumeration) and passes with this change.
- Validation harness: 54 passed; `scenarios/test_folder_inventory.py` collects its four cases. Not run against a live stack.
- Prior label-filter tests used SQLite only. The folder-inventory live scenario calls tabular APIs and does not exercise the three label queries on PostgreSQL.

## 4. Confidentiality correction and review

- [ ] 4.1 Confirm base/HEAD behavior with real SQL and deterministic barriers; inspect title, name, retrievability, resource content and ingestion writes
- [ ] 4.2 Restore bounded candidate checks for metadata, labels, resources and tabular operations, preserving scopes and special authorization paths
- [ ] 4.3 Prove denial for A and retained access for B across all affected surfaces, exact pagination, error propagation, and 1,500/3,000-document completeness
- [ ] 4.4 Exercise all three label query filters on real isolated PostgreSQL and report separately from SQLite and OpenFGA doubles
- [ ] 4.5 Run required tests/root quality, independent full review and correction review; reconcile documentation and PR evidence
