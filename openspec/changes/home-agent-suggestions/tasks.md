# Tasks

## 1. SQL-backed discovery
- [x] 1.1 Add nullable activity and index with a linear Alembic migration; verify head and migration upgrade on an isolated database.
- [x] 1.2 Reuse explicit owner-scoped activity PATCH with server timestamps; test no activity on rename and no regression.
- [x] 1.3 Implement bounded ranked instance query and permission-scoped product endpoint; test filtering, backfill, ties, personal-only and partial failure. Document contract and migration.

## 2. Home integration
- [x] 2.1 Regenerate control-plane API using make update-control-plane-api; replace home fan-out with the generated hook; test loading/error/retry and five cards. Update UX docs.

## 3. Integration and review
- [ ] 3.1 Run focused tests, required quality checks, independent author/performance review; record evidence and fix findings.

## Workflow follow-up
- Sync and archive after verification and required review; push a draft PR linked to #3510.

Verification so far: 54 targeted backend tests; 4 frontend tests; raw backend basedpyright and frontend tsc pass. Migration upgrade/downgrade tested on isolated SQLite, one Alembic head. Fifty concurrent home queries through two SQL pools preserve ordering and five-result bounds. Root quality stopped at an unrelated web-research virtualenv bootstrap (missing pip); retry pending. Independent read-only review against e01f8e25c found no implementation defect and identified unrelated inherited ancestry, to isolate before PR.
