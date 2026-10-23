# Verification

The worktree venv could not be synced (package downloads timed out), so tests ran with the main checkout's venv on the worktree code, from `apps/knowledge-flow-backend` (`knowledge_flow_backend.__file__` confirmed to resolve to the worktree):

    PYTHONPATH=<worktree>/apps/knowledge-flow-backend <main>/apps/knowledge-flow-backend/.venv/bin/python -m pytest ...

## Proven

- Focused offline tests (`-m "not integration" --disable-socket --allow-unix-socket`): `tests/stores/test_pgvector_store.py`, `tests/features/test_metadata_service_retrievable.py`, `tests/features/test_metadata_service_labels.py`, `tests/features/test_folder_derived_listing.py` — 68 passed.
- Real pgvector (`tests/stores/test_pgvector_store_postgres.py -m integration`, `FRED_PGVECTOR_DSN` on a disposable `pgvector/pgvector:pg15` container): 2 passed. Off/on round trip updates only the target document's chunks and `ann_search` hides then returns it; a legacy chunk without the field is searchable until toggled off. The adapter ran on the legacy `langchain_community` store, the one deployments currently get (see design non-goals).
- Full Knowledge Flow offline suite (`-m "not integration" --disable-socket --allow-unix-socket`): 1608 passed, 2 skipped, 47 deselected.
- `ruff check` and `ruff format` on the touched files: clean.
- `scripts/migration_guides.py check-pr --base fix/3209-public-team-sessions --worktree`: 1 new declaration valid.
- Performance review: the vector toggle, previously a blocking call inline in the coroutine, now runs in `asyncio.to_thread` for every store. The search path is unchanged. No KPI or label added.

## Not proven

- A live end-to-end HTTP toggle plus hybrid search on a deployed pgvector stack.
- `make code-quality` (basedpyright) for the module; left to the root run.
- OpenAPI unchanged by inspection (no route, model or response declaration touched); no client regeneration.
