## Verification

All commands ran from the change's worktree on 2026-10-22. The worktree venv could not be synced (package downloads hung), so tests used the main checkout's Knowledge Flow venv with the worktree code first on `PYTHONPATH`; `knowledge_flow_backend.__file__` was confirmed to resolve to the worktree.

| Check | Command (from `apps/knowledge-flow-backend`) | Result |
| --- | --- | --- |
| Focused audit tests | `PYTHONPATH=$PWD <main-venv>/bin/python -m pytest tests/features/test_metadata_audit.py -q` | 7 passed |
| Regression proof | Same command with `service.py` reverted to the base branch | 2 failed (session attachment reported; no classification warning), 5 passed |
| Offline unit suite (`make test` markers) | `PYTHONPATH=$PWD <main-venv>/bin/python -m pytest -m "not integration" --disable-socket --allow-unix-socket -q` | 1604 passed, 2 skipped, 45 deselected |
| Lint / format | `<main-venv>/bin/ruff check` and `ruff format --check` on `service.py` and the audit test | clean |
| Migration note | `<main-venv>/bin/python scripts/migration_guides.py check-pr --base fix/3209-public-team-sessions --worktree` (repo root) | 1 new declaration valid |
| OpenSpec | `openspec validate exclude-session-vectors-from-corpus-audit --strict` | valid |

`<main-venv>` is `/home/thomas/Documents/fred/apps/knowledge-flow-backend/.venv`.

## Proven

- A session attachment (all chunks marked `scope: session`) beside a corpus orphan: only the orphan is reported; `vector_count` still counts both; the metadata-backed UID is never classified.
- Chunk lookup raising `NotImplementedError` keeps `orphan_vectors` (base hook returns `False`).
- Chunk lookup raising another error keeps `orphan_vectors` and logs a warning naming the UID and error.

## Not proven

- Real adapters (OpenSearch, pgvector, ClickHouse, Chroma) persisting and returning the `scope` chunk metadata; the tests drive the real `BaseVectorStore.is_session_scoped_document` with a fake chunk lookup.
- Audit latency on a platform with many attachments (one chunk lookup per vector-only UID).
- Root `make code-quality` (basedpyright) — left to the integration run.
