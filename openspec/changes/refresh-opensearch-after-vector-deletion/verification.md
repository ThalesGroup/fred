# Verification

All commands run from `apps/knowledge-flow-backend` of this branch's worktree. `make dev` could not
download dependencies (network timeouts), so tests ran with an existing Knowledge Flow virtualenv while
importing this worktree's code (`knowledge_flow_backend.__file__` resolved to the worktree):

```bash
PYTHONPATH=$PWD <existing-kf-venv>/bin/python -m pytest <args>
```

## Proven

- Regression test `test_delete_vectors_for_document_refreshes_so_deletion_is_immediately_visible`
  asserts `delete_by_query` receives `{"conflicts": "proceed", "refresh": "true"}` for the document term
  query. It fails against the pre-fix adapter (`1 failed`) and passes with the fix.
- `pytest tests/stores/test_opensearch_vector_store.py`: 26 passed.
- Offline suite, equivalent to `make test` without coverage
  (`pytest -m "not integration" --disable-socket --allow-unix-socket`): 1602 passed, 2 skipped,
  45 deselected.
- `ruff check` and `ruff format --check` on the two touched Python files: all checks passed, already
  formatted.
- `openspec validate refresh-opensearch-after-vector-deletion --strict`: valid.
- Migration note: `scripts/migration_guides.py check-pr --base fix/3209-public-team-sessions --worktree`:
  1 new declaration valid.

## Not proven

- No live OpenSearch integration check was run: an immediate count/search after deletion against a real
  index is not exercised. The guarantee rests on OpenSearch's documented `refresh=true` semantics for
  `delete_by_query`.
- `make test` itself (with coverage) and root `make code-quality` were not run from this worktree.
