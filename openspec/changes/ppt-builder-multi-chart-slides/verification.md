## Verification (2026-10-16)

In `libs/capabilities/fred-capability-ppt-filler`, with the module's `.venv/bin/uv`:

- `make code-quality`: ruff check, `ruff check --select I`, `ruff format --check`, bandit, detect-secrets clean; basedpyright 0 errors (1 pre-existing warning in `tests/builder_decks.py`).
- `make test`: 834 passed, 5 skipped (17 new in `tests/test_multi_chart_slides.py`).
- `make builtin-inventory`: the built-in inventory changes only by its `analysis_version` (16); its chart slides are unchanged.
- `openspec validate ppt-builder-multi-chart-slides --strict`: valid.
- Help Center guides: `npx prettier --check` clean on both files.

What the tests prove, on a template shaped like the owner's (one-, two-, three- and four-chart example slides, frames drawn out of reading order):

- Analysis: 2 × 24 %, 3 × 15 % and 4 × 9.3 % frames are chart slides with that many zones, in reading order; the catalogue says `charts×N`. Five charts, or a frame under 1/20 of the slide, keep the slide out (`unsupported_parts`, `chart` for five large ones in the showcase deck).
- Plan: `chart` and `charts` together are refused; data problems, the one-measure check and the missing title each name `charts[i]`.
- Assignment: 1, 2, 3 and 4 charts each take the slide with exactly as many frames, one chart its one-chart slide; 3 charts on a 1/2/4 template are refused with "this template offers slides with 1, 2 or 4 charts", split and merge options; a long-labelled chart in the small grid is measured on its own frame; the variety ask never offers a slide with another number of charts (fails before that fix).
- Rendering: a column then a pie example are refilled in place (formatting kept, two chart parts, no `srgbClr`); the grid takes four charts in reading order with four parts; a text box right above each frame shows that chart's title and the chart none; a delivered slide with fewer charts than planned stops the build.
- Edits: `charts[1].series[0].values[2]` changes one value and keeps the template slide; `chart.type` on a two-chart slide is refused naming `charts[i].type`; sending four charts moves the slide to the four-chart one.
- Tool: `charts` is in the schema, the guide and the `changes` examples only when a template slide holds several charts; units written beside values reach the one-measure check.

Owner's template (`Thales_PPT_Template_FR_11032026.pptx`, which already holds a three-chart slide): analysis keeps slides 20 to 25 as chart slides (`chart`, `charts×2`, `charts×3`, `charts×4`, two side slides). A 5-slide deck with 1, 2, 3 and 4 charts was assigned with no problem, rendered with 1, 2, 3 and 4 native charts each on its own part, and converted through LibreOffice (`~/fred-tmp/multi-chart/owner-multi-chart.pdf`, not committed): the example charts keep their format and take the plan's data. On the 2 × 2 grid, the example charts' own title format overlays the plot area at that size (template formatting, kept by design).

Divergences from design.md, kept on purpose:

- D1: frames that pass the tests become zones, up to four; any chart left out keeps the slide excluded by the existing rules. Same included/excluded outcome as "all or none", and the exclusion reason stays the current one, as the spec requires.
- D4: the heading box is paired from the pattern's zone geometry when read (`plan.chart_headings`), not stored at analysis: no `Zone` field, so no API or generated-client change. Pairing applies only on slides with two charts or more, so a one-chart slide behaves exactly as before.
- Tests sit in one new file, `tests/test_multi_chart_slides.py`, rather than spread over six files.

Not proven: a live `make eval` run (`charts_pair`, `charts_grid` and their edits are added) and a build through the agent in the running app.
