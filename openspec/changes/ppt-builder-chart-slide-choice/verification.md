## Verification (2026-10-16)

In `libs/capabilities/fred-capability-ppt-filler`, with the module's `.venv/bin/uv`:

- `make code-quality`: ruff check, `ruff check --select I`, `ruff format --check`, bandit, detect-secrets clean; basedpyright 0 errors (1 pre-existing warning in `tests/builder_decks.py`).
- `make test`: 817 passed, 5 skipped.
- Regression: `test_a_bare_chart_keeps_the_centred_slide_and_text_alternates_the_sides` fails on the code before this change (the second bare chart takes a side slide) and passes after.
- Built-in: `test_a_takeaway_goes_beside_the_chart_and_a_bare_chart_spans_the_slide` passes unchanged.
- `openspec validate ppt-builder-chart-slide-choice --strict` and `openspec validate ppt-builder-charts --strict`: valid.

Not proven: a live build on the owner's template (session 693bd457); the regression test reproduces its three chart slides synthetically.
