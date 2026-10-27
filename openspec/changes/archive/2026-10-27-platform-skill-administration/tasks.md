## 1. Inventory

- [x] 1.1 Publish authorized packaged runtime inventory and aggregate bounded source reads; verify empty/unreachable/unsupported/custom cases (#3301).
- [x] 1.2 Render global Administration > Features > Skills with metadata and availability; verify public UI authorization/states.

## 2. Enablement

- [x] 2.1 Persist atomic per-skill exceptions and audit metadata; verify independent stores/concurrent updates and linear migration (#3303).
- [x] 2.2 Resolve trusted policy per turn/resume and negotiate enforcement version; verify old runtimes fail closed with active restrictions.
- [x] 2.3 Apply runtime views and deny new loads across all read paths/children; verify two-pod/open-conversation and native pin cases.
- [x] 2.4 Connect admin toggles and truthful failure states; verify disabling and re-enabling.

## 3. Integration

- [x] 3.1 Regenerate API clients, document rollout/rollback, run root quality/offline and focused concurrency checks plus independent performance/spec review; reconcile and archive.

Evidence: full control-plane offline suite passes 2081 tests (10 skipped,
13 integration tests deselected). Subsequent offline retry correction has a
red/green recovery regression and 9 passing store/service tests. Independent
store instances and concurrent per-name writes are covered. Real SQLite Alembic
upgrade/check/downgrade/re-upgrade succeeded with one linear head. Runtime
compiled tests cover a second executor sharing checkpoint state, new policy on
resume, denied native searches/capability reads and twelve concurrent pin runs.
Production PostgreSQL contention, a live multi-pod rollout and p99 load were not
exercised; migration ordering and mixed-version limits are documented in the
rollout note. No process-local policy cache is used for correctness.

After final import normalization, 61 focused administration, store, CLI,
authorization and endpoint-matrix tests pass.
