## 1. Visible truncation for remaining enumerations

- [x] 1.1 `OpenFgaRebacEngine._lookup_resources_raw` keeps plain `list_objects` and warns at 1,000 results or 2.5 s
- [x] 1.2 Tests: warning at the result limit, near the deadline, and none below both

## 2. Readable documents from authorized folders

- [x] 2.1 Tabular `_resolve_authorized_datasets` builds candidates from scope tags (or readable tags when unscoped); tabular candidates require READ and the service-agent exception remains explicit
- [x] 2.2 `MetadataService.get_documents_metadata` and the three label methods check candidates from readable tags
- [x] 2.3 Label store methods narrow by `tag_ids` instead of `document_uids`
- [x] 2.4 `ResourceService.list_resources_by_kind` checks candidates from readable tags

## 3. Verification

- [x] 3.1 Offline: tabular list/describe/query/search with 1,500 and 3,000 readable documents, target outside the first 1,000, and a fake that fails on any document enumeration
- [x] 3.2 Offline: labels over a 1,500-document folder, document and resource listings narrowed by readable folders
- [ ] 3.3 Validation scenario: 3,000-document corpus with a tabular target (run by the developer on k3d)
- [x] 3.4 Migration note, impact none, truncation-warning guidance
- [ ] 3.5 Record k3d evidence; archive once complete

## Verification evidence

- Base `39aabba0a926359bf9318483417026101cd049fd` retains the stale full-write lost update but denies the reproduced reads. Original PR head `a5d6d805d5a3304dcb8b2dc1a30263d7084de948` exposes them: 14 deterministic race/historical-drift regressions and 13 new tabular cases fail there. Corrected code passes all 31 drift tests and 113 tabular tests, retaining 1,500/3,000-document cases.
- `make -C libs/fred-core test`: 1,279 passed, 1 skipped (optional fastapi_mcp unavailable), 49 integration cases deselected.
- `make -C apps/knowledge-flow-backend test`: 1,601 passed, 2 skipped, 45 deselected; 31 warnings include deprecations and SQLite worker shutdown. The new pagination test explicitly disposes its engine.
- Root `make code-quality` passes across all modules. It reports five unreachable-code warnings in unchanged runtime files and an npm engine-version warning; these are not a claim of zero warnings.
- Real PostgreSQL 17.11: all 18 tests in `test_postgres_document_store_sql.py` pass, including seven new cases exercising all three label queries and a 32,768-folder array. Prior SQLite tests and the tabular-only live scenario did not establish this coverage.
- Real PostgreSQL 17.11 + OpenFGA 1.15.1 service/store replay passes both title and resource-rename races: one document/label, one prompt, two folders, three users, eight initial tuples, two overlapping requests per race. SQL ends at [A,B], FGA at [B]; A is denied, B retains access. This does not cover HTTP middleware, quota transfer, tabular/vector ingestion or load.
- Validation harness: 45 passed; the initially skipped cross-repository module then passes all nine cases with `FRED_DEPLOYMENT_FACTORY_SRC` set (54 total).
- Fresh independent full review through `47627fd066105dfe57bed7568ee05bb4bf60c409` plus documentation found only inaccurate concurrency/call-count wording. Both corrections were re-reviewed; no outstanding actionable finding remained. Review coverage, verification results and limits are recorded in PR #3181.
- Strict OpenSpec validation, migration-note validation and whitespace checks pass. Live k3d and production-scale load evidence remain pending; keep this change active.

## 4. Confidentiality correction and review

- [x] 4.1 Confirm base/HEAD behavior with real SQL and deterministic barriers; inspect title, name, retrievability, resource content and ingestion writes
- [x] 4.2 Restore bounded candidate checks for metadata, labels, resources and tabular operations, preserving scopes and special authorization paths
- [x] 4.3 Prove denial for A and retained access for B across all affected surfaces, exact pagination, error propagation, and 1,500/3,000-document completeness
- [x] 4.4 Exercise all three label query filters on real isolated PostgreSQL and report separately from SQLite and OpenFGA doubles
- [x] 4.5 Run required tests/root quality, independent full review and correction review; reconcile documentation and PR evidence
