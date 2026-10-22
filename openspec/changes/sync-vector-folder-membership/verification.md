## Verification evidence

The worktree could not sync its own venv (network downloads stalled), so tests
ran with the main checkout's venv importing the worktree's code, from
`apps/knowledge-flow-backend`:

```
PYTHONPATH=$PWD /home/thomas/Documents/fred/apps/knowledge-flow-backend/.venv/bin/python -m pytest -p no:cacheprovider <args>
```

`python -c 'import knowledge_flow_backend; print(knowledge_flow_backend.__file__)'`
resolved to the worktree. chromadb 1.5.9, langchain-postgres 0.0.17.

- Touched tests (`tests/features/test_metadata_folder_links_reach_vectors.py`,
  `tests/stores/`, `tests/features/library_sync/`): 237 passed.
- Full offline suite, `-m "not integration" --disable-socket --allow-unix-socket`:
  1617 passed, 2 skipped, 45 deselected.
- Regression check: with `service.py` and the Chroma adapter reverted, the four
  link/unlink/failure service tests, the refile test and the Chroma folder
  tests fail (Chroma cannot be instantiated without the new abstract method).
- The Chroma filter commit alone (exported with `git archive`): Chroma tests
  5 passed, including multi-folder ingestion and one-folder JSON chunks.
- ruff format and ruff check: clean on all touched files. basedpyright was not
  run (the borrowed venv does not resolve the worktree's imports); root
  `make code-quality` remains to run.
- `scripts/migration_guides.py check-pr --base origin/swift --worktree`
  (main venv python; `uv` is not on PATH): valid.
- `openspec validate sync-vector-folder-membership --strict`: valid.

Live pgvector (throwaway `pgvector/pgvector:pg15` container): the adapter's
`set_document_tag_ids` rewrote the folders of three chunks to `["alpha","beta"]`
then `["beta"]`, read back through `get_chunks_for_document`. PostgreSQL
confirmed the pushed-down `$.tag_ids == $value` jsonpath matches one member of a
multi-folder array. A filtered `ann_search` returned nothing, before and after
the link, for a pre-existing reason: `PgVectorStoreAdapter._create_store` never
passes `connection` to langchain-postgres 0.0.17, falls back to the legacy
langchain-community `PGVector`, and every metadata-filtered query fails with
`function jsonb_path_match(jsonb, character varying, character varying) does not
exist`, swallowed into an empty result. Not fixed here.

Not verified: OpenSearch against a live cluster (fake client only), ClickHouse
against a live server (fake client only), an end-to-end search through the API.

## Performance review

- Search hot path unchanged; no per-query lookup added.
- Link/unlink add one synchronous store call per vectorized document, offloaded
  with `asyncio.to_thread` (no event-loop blocking): one `update_by_query` with
  `refresh=true` (OpenSearch), one `UPDATE` (pgvector), one synchronous mutation
  (ClickHouse), one get+update (Chroma).
- Bulk folder edits (`TagService.update_tag` gathers every added/removed item)
  now issue one such call per document, bounded by the default thread pool; on
  OpenSearch that is one refresh per document. Same profile as rename and
  retrievability; acceptable for user-driven edits, worth a batch API if large
  folder imports by link become common.
- No new KPI, metric label, shared client or cache. Store calls use each
  client's existing timeout configuration (none added).
