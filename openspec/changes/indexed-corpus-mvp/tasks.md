Groups 1-6 are already implemented and merged on `feat/pull-corpus`, recorded here as done with their verification, not proposed. Group 7 is next. Group 8 depends on Group 7 landing. Do not batch remaining groups into one uninterrupted pass — each stays its own scoped commit, per this project's convention.

## 1. Core contracts (`fred-sdk`)

- [x] 1.1 Add `CorpusType`, `Corpus`, `CorpusScope`, `CorpusMode`, `CorpusKind` to `libs/fred-sdk/fred_sdk/contracts/corpus.py`, with the mode/connector_kind exclusivity invariant on `CorpusType`. Verify: `libs/fred-sdk/tests/test_corpus_contracts.py` (13 tests) passes; `make code-quality` clean.
- [x] 1.2 Add `SourceItem`, `SourceChange`, `ChangeKind`, `SourceConnector` to `libs/fred-sdk/fred_sdk/contracts/connector.py`. Verify: same test file, including the in-memory fake proving the Protocol is implementable.

## 2. First `SourceConnector` implementation

- [x] 2.1 Implement `LocalFilesystemConnector` (`apps/knowledge-flow-backend/knowledge_flow_backend/core/connectors/local_filesystem_connector.py`) — content-hash revision, not mtime. Verify: `tests/core/connectors/test_local_filesystem_connector.py` (6 tests) passes against a real temporary directory, including the case where content changes but mtime does not.

## 3. Sync wiring into the existing push pipeline

- [x] 3.1 Implement `sync_pull_corpus` (`apps/knowledge-flow-backend/knowledge_flow_backend/features/scheduler/pull_corpus_sync.py`), reusing `extract_metadata`/`save_input`, `push_input_process`, `output_process`, `delete_document_and_artifacts`. Verify: `tests/features/scheduler/test_pull_corpus_sync.py` (6 tests, mocked ingestion primitives) covers upsert, delete, changed-content (delete-then-recreate), and no-op.

## 4. Prior cleanup (predates this design, listed for the record)

- [x] 4.1 Removed untested/dead pull-mode scaffolding that predated this design (old content loaders, dead catalog store, unwired Sphere/GitHub/Gitlab config, unreachable branches this left behind). Verify: full offline test suite green at the time, no behavior loss (nothing removed had test coverage).

## 5. `corpus_type` usage-enablement gate (`fred-core`)

- [x] 5.1 Add `type corpus_type` to `libs/fred-core/fred_core/security/rebac/schema.fga` (organization/default_on/enabled/disabled/can_manage/can_use; no personal-space overlay), regenerate `schema.fga.json` via `make transform-openfga-schema`. Verify: JSON regeneration diff is scoped to the addition only.
- [x] 5.2 Add `Resource.CORPUS_TYPE`, `CorpusTypePermission`, and `can_team_use_corpus_type` (`fred_core/security/rebac/corpus_type_authz.py`). Verify: `fred_core/tests/security/test_corpus_type_authz.py` (3 tests) passes.

## 6. `CorpusType` config and `Corpus` persistence (`control-plane-backend`)

- [x] 6.1 Add `CorpusTypeConfig` as deployment configuration (`control_plane_backend/corpus_types/catalog.py`), subclassing `fred_sdk.contracts.corpus.CorpusType` rather than redeclaring its fields, mirroring `ApplicationSourceConfig`. Verify: `tests/test_corpus_types.py` (3 tests).
- [x] 6.2 Add the `corpus` table (`control_plane_backend/models/corpus_models.py`) and `CorpusStore` (`control_plane_backend/corpus/store.py`), reading/writing `fred_sdk.contracts.corpus.Corpus` directly. Verify: `tests/test_corpus_store.py` (4 tests, real SQLite engine); migration `alembic/versions/57f8e7e05006_add_corpus.py` passes `make db-check-heads` and `make db-check-sqlite` (full upgrade/check/downgrade cycle).
- [x] 6.3 Add `create_corpus` (`control_plane_backend/corpus/service.py`), failing closed on an unregistered/disabled corpus type, then on a team lacking `can_use`. Verify: `tests/test_corpus_service.py` (4 tests).

## 7. M2M read path and `knowledge-flow-backend` consumption (not yet started)

- [ ] 7.1 Add a minimal M2M read endpoint on `control-plane-backend` returning one `Corpus` plus its `CorpusType` by `corpus_id`, authenticated the same way `control-plane-backend`'s other M2M surfaces are. Verify: a contract test exercising the endpoint with the runtime M2M client identity, and a denial test for any other caller.
- [ ] 7.2 Add a small `corpus_sync_state` table in `knowledge-flow-backend` (`corpus_id`, `state`, `updated_at`), next to `kf_task_run`/`kf_task_event_log` — this table, not control-plane, owns the sync cursor/document-id map (design.md D7). Verify: a store-level test with a real SQLite engine, mirroring `tests/features/test_task_store.py`'s pattern; an Alembic migration passing `make db-check-heads`/`make db-check-sqlite` in `knowledge-flow-backend`.
- [ ] 7.3 Update `sync_pull_corpus` to fetch `Corpus`/`CorpusType` via the Task 7.1 endpoint once per sync cycle (not per file) instead of receiving them as plain arguments, and to read/write its state through the Task 7.2 store. Verify: `tests/features/scheduler/test_pull_corpus_sync.py` updated and passing with the M2M call and the new state store both exercised (mocked at the boundary, per this file's existing test convention).

## 8. Validate the no-overlapping-synchronization requirement end to end

- [ ] 8.1 Add a test that starts two synchronizations for the same corpus instance concurrently and verifies the second does not run against the same state while the first is in progress (specs/indexed-corpus/spec.md - "A corpus instance never runs two overlapping synchronizations"). The concrete mechanism (a lease, a lock, a workflow-id uniqueness guarantee) is an implementation choice not fixed by design.md; pick one and document it in this task's completion note.
