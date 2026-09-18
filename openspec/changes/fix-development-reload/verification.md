# Verification

- `python scripts/tests/test_python_run.py`: 2 tests pass with Uvicorn 0.35.0 / watchfiles 1.2.0. Covers all three backend command scopes, both reload targets, non-reloading run-prod, and real watcher notifications for app code, every declared local package and YAML.
- Same tests with Uvicorn 0.34.0: three backend scope subtests fail because the supervisor adds the working directory. This justifies upgrading knowledge-flow 0.34.0 and control-plane 0.34.3 to 0.35.0.
- Ruff lint, import order, formatting and `git diff --check` pass for the new test.
- Locks regenerated with `uv lock --project apps/<backend>`; only Uvicorn versions change and watchfiles is added for fred-agents. Knowledge-flow's resolver also normalizes platform markers; no unrelated package versions change.
- Root `make code-quality` and `make test` are still running in the isolated checkout; final results and independent review remain pending.
- No live backing services or full backend boot exercised; tests drive Uvicorn's real reload supervisor directly.
