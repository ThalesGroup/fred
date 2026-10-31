Linked issue: #3144. Apply after `ppt-builder-charts`, `ppt-builder-more-chart-types` and `ppt-builder-storytelling`; owner decisions recorded in design.md (2026-10-16).

## 1. Analysis

- [x] 1.1 `analysis.py` step 4c: every eligible chart frame ≥ `_GRID_CHART_AREA` (0.05), at most `MAX_CHARTS_PER_SLIDE` (4), all-or-none, appended in reading order (design D1)
- [x] 1.2 `analysis.py`: pair a free text box directly above a chart frame as that chart's heading (D4, per Owner decision 3)
- [x] 1.3 `analysis.py`: `ANALYSIS_VERSION` 16; `make builtin-inventory`
- Verification: `test_builder_analysis.py` — two 24 % charts → 2 zones left-to-right, included; four 9.3 % charts in a grid → 4 zones in reading order, included; one 3 % unkept chart → excluded as today; five charts → excluded

## 2. Plan and validation

- [x] 2.1 `plan.py`: `SlidePlan.charts`, `slide_charts()` helper, `chart` + `charts` together → problem (D2)
- [x] 2.2 `story.py`: `_units`, `_spread`, `slide_figures` per chart, problems prefixed `charts[i]`; title required when k ≥ 2; `notes.py` caption per chart (D4)
- Verification: `test_plan_validation.py`, `test_story_checks.py` — both fields refused, `charts[1]` unit mix named, untitled chart named

## 3. Assignment

- [x] 3.1 `assign.py`: chart capacity per pattern, exact-count misfit, per-pair `fit_problems` prefixed `charts[i]` (D3)
- [x] 3.2 `assign.py`: `_chartless`/`_chart_options`/`_substitution` advice listing the offered counts (split, merge, drop)
- Verification: `test_assign.py` — 2 charts → 2-chart slide; 1 chart never lands on the 2-chart slide; 3 charts on a 1/2/4 template refused with the offered counts

## 4. Rendering and after-render check

- [x] 4.1 `render.py`: `chart_hosts` and `_fill_chart` per pair (refill on type match, else draw), notes naming chart i (D5); heading box filled from `charts[i].title`
- [x] 4.2 `checks.py`: native chart count with resolvable parts equals the plan's (D7)
- Verification: `test_chart_slides.py` — 2-chart and 4-chart slides delivered with N charts, each with its own part, `schemeClr` only, example formatting kept on type match; evidence PDFs through LibreOffice in `verification.md`

## 5. Edits and model guidance

- [x] 5.1 `changes.py`: `charts` in `_SLIDE_KEYS` and the shape table; `chart.…` on a multi-chart slide refused with its fix; list length change re-assigns (D6)
- [x] 5.2 `tools.py`: `charts` in the schema only with a multi-chart slide; catalogue `charts×k`; guide pair and field description (D8)
- Verification: `test_deck_changes.py` (edit `charts[1].series[0].values[2]`; `chart.type` on a 2-chart slide refused), `test_build_tool.py` (schema and description assertions)

## 6. Evaluation, docs, close-out

- [x] 6.1 `eval/prompts.py`: `charts_pair`, `charts_grid`, an edit on `charts[1]`, metrics of D9 (live `make eval` run separate)
- [x] 6.2 Help Center fr+en `guides/prepare-powerpoint-template.md`, package `README.md` (D9)
- [x] 6.3 Migration-note line in `docs/swift/ops/migrations/ppt-builder-capability.md` (impact none, patch)
- [x] 6.4 Package `make test`, `ruff check` (incl. `--select I`), `ruff format --check`, basedpyright; `openspec validate ppt-builder-multi-chart-slides --strict`
- [x] 6.5 Test on the owner's template: the 2-chart and 4-chart example slides are offered and filled; `verification.md` with test counts and evidence; archive after the three changes it extends (done: owner's template and evidence; remaining: archive)
