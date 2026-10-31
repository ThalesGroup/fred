## 1. Plan model

- [x] 1.1 `plan.py`: `CHART_TYPES` + `stacked_bar`, `radar`, `scatter`, `bubble`; aliases of design D1 (`stacked bar` → `stacked_bar`); type enum descriptions of D6
- [x] 1.2 `plan.py`: `PlanPoint {x, y, size, label}` and `PlanSeries.points` with the D2 coercions (lists, objects, parallel lists, chart-level `x` for XY types, numeric categories → x); unread text kept as gaps; per-axis unit inference
- [x] 1.3 `plan.py`: `x_title`, `x_unit`, `y_title`, `size_title`, `size_unit` with aliases; `x_axis`/`y_axis` objects stay style keys; `stacked_as` valid for `stacked_bar`
- Verification: `test_chart_slides.py` coercion cases (each point form, numeric categories, `stacked bar` alias, `x` read as categories for column and as x values for scatter)

## 2. Validation and fit

- [x] 2.1 `charts.py` `data_problems`: D3 rows (shape vs type, numeric points, axis titles, bubble sizes, size on scatter, caps, radar 3–8 categories and ≤ 3 series), each message with its remedy
- [x] 2.2 `charts.py` `fit_problems`: `stacked_bar` as `bar`; radar label room; scatter/bubble axis titles, series names and title room
- [x] 2.3 `story.py`: `stacked_bar`, `radar` in `_SPREAD_TYPES`; per-axis units for scatter/bubble, no spread question; `slide_figures` reads x, y, size; `highlight` on a point label, `sort` note on scatter/bubble/radar
- Verification: one test per D3 message and per D4 rule (`test_chart_slides.py`, `test_story_checks.py`)

## 3. Rendering

- [x] 3.1 `charts.py`: `XL_TYPES` and `_FROM_XL` for the four types; `_data` builds `XyChartData`/`BubbleChartData`; markers and fills with theme accents; scatter without lines; bubble scale
- [x] 3.2 `charts.py` `_axes`: axis titles `"<title> (<unit>)"`, per-axis number formats; bubble `size_title` as the caption's second line; point labels per Q2's answer
- [x] 3.3 `charts.py` `refill`: phase B reuse for the four types when the example chart matches; else `draw`
- [x] 3.4 `analysis.py`: `ANALYSIS_VERSION` 15; `make builtin-inventory`
- Verification: each type builds and reopens with `has_chart`, chart XML holds `schemeClr` and no `srgbClr`, axis titles present; evidence PDFs of the four types through LibreOffice in `verification.md`

## 4. Edits and model guidance

- [x] 4.1 `changes.py`: paths `chart.series[j].points[i]`, `.x`, `.y`, `.size`, `.label`, `chart.x_title`, `chart.x_unit`, `chart.y_title`, `chart.size_title`, `chart.size_unit`; re-validation names a shape problem after a `chart.type` edit across shapes
- [x] 4.2 `tools.py`: field line, `_guide` pairs and edit paths of D6; catalogue lists the eleven types
- Verification: `test_deck_changes.py` (edit a point, change scatter → column refused with its message), `test_build_tool.py` description assertions

## 5. Evaluation, docs, close-out

- [x] 5.1 `eval/prompts.py`: the four prompts and edits of D7, metrics (type chosen, first-call success, axis titles) — harness only, needs a live LLM (prompts, edits and metrics written; the `make eval` run against a live model is still to do) — live run 2026-10-25 through the revision harness (`~/fred-tmp/revision-evals/charts-r1..r3`), not `make eval`: scatter, bubble, radar and stacked bar chosen as asked; bubble pass r1-r3, stacked+bubble pass in r3; r3 6/3/0 on 9 requests, r2 6/6/1 on 13
- [x] 5.2 Help Center fr+en: `guides/prepare-powerpoint-template.md` chart types, `features/capabilities.md` chart sentence; package `README.md`; check whether the generated client carries the type enum and regenerate if so
- [x] 5.3 Migration note line (impact none, patch); package `make test`, `ruff check` (incl. `--select I`), `ruff format --check`, basedpyright baseline; `make code-quality`/`make test` for frontend if touched; `openspec validate ppt-builder-more-chart-types --strict`
- [x] 5.4 `verification.md` with test counts and evidence (written); archive after `ppt-builder-charts` and `ppt-builder-storytelling`
