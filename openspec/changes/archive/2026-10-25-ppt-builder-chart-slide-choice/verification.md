## Verification (2026-10-16)

In `libs/capabilities/fred-capability-ppt-filler`, with the module's `.venv/bin/uv`:

- `make code-quality`: ruff check, `ruff check --select I`, `ruff format --check`, bandit, detect-secrets clean; basedpyright 0 errors (1 pre-existing warning in `tests/builder_decks.py`).
- `make test`: 817 passed, 5 skipped.
- Regression: `test_a_bare_chart_keeps_the_centred_slide_and_text_alternates_the_sides` fails on the code before this change (the second bare chart takes a side slide) and passes after.
- Built-in: `test_a_takeaway_goes_beside_the_chart_and_a_bare_chart_spans_the_slide` passes unchanged.
- `openspec validate ppt-builder-chart-slide-choice --strict` and `openspec validate ppt-builder-charts --strict`: valid.

Not proven: a live build on the owner's template (session 693bd457); the regression test reproduces its three chart slides synthetically.

## D6 (2026-10-17): an empty takeaway card weighs two zones

`test_chart_slides.py::test_bare_charts_all_span_the_slide_even_with_variety` (four bare charts with a takeaway in the notes, `variety_max_uses` 1) fails before (the takeaway slide alternates in), passes after. Three `test_chart_intents.py` tests about the card slide's own column chart now pin that slide (`built_on`), since a bare chart no longer lands on it. Showcase (`~/fred-tmp/default-template/v3-fixes/`): every bare chart of deck A on the full-width slide; deck B (takeaways shown) on the card slide with the card filled; chart with figures unchanged. Commands: package `make code-quality` clean (ruff, `--select I`, format, bandit, detect-secrets; basedpyright 0 errors, the pre-existing `builder_decks.py` warning); `make test`: 903 passed, 5 skipped; `openspec validate --strict` on the three changes.
