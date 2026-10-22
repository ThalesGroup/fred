## Verification

All commands ran from `apps/control-plane-backend` of the branch worktree with the
main checkout's virtualenv (`<main>/apps/control-plane-backend/.venv/bin/python`).
`python -m` puts the working directory first on `sys.path`, so
`control_plane_backend` imports from the worktree; `uv sync` could not complete
(download timeouts), so `make test` was not used.

- Regression: `python -m pytest -q tests/test_capability_selection_1974.py`
  - 38 passed, including the two new exempt-instance tests and the retained
    `test_update_rejected_once_template_access_is_revoked`.
  - With the `product/service.py` fix reverted, both new tests failed with the
    403 "template access has been revoked" detail; the revoked ordinary-template
    test still passed.
- Module unit suite (`make test` options without coverage):
  `python -m pytest -q -m "not integration" --disable-socket --allow-unix-socket -p no:cacheprovider`
  - 2013 passed, 10 skipped, 13 deselected.
- Lint: `ruff check` and `ruff format` on the two touched Python files: clean,
  unchanged.
- Migration note: `make migration-check MIGRATION_BASE=fix/3209-public-team-sessions`
  - "Migration notes valid: 1 new declaration(s)".
- OpenSpec: `openspec validate fix-self-test-agent-updates --strict`: valid.

Not verified: a live self-test run against a deployment (agents family
disable/enable and prompt update over HTTP).
