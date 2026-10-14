## Phase A — fresh native charts

### 1. Models and analysis

- [ ] 1.1 `models.py`: `chart` in `ZoneRole` and `SlideKind`; `Zone.chart_capable: bool`; `Zone.chart_type: Optional[str]` (the example chart's type, read by phase B); `"chart"` kept in `ExclusionReason` (two main charts on one slide)
- [ ] 1.2 `analysis.py`: `CHART` placeholder → `chart` zone (layouts and slides); the one example-slide chart frame ≥ `_MAIN_CONTENT_AREA` → `chart` zone instead of exclusion; its `/chart` relationship accepted, any other chart relationship still uncopyable; `OBJECT` placeholder ≥ `_CHART_MIN_AREA` → `chart_capable`; `_kind` returns `chart` when a chart zone is present; `ANALYSIS_VERSION` 12
- [ ] 1.3 `labelling.py`: `chart` in the vision vocabulary; compatibility "a chart zone needs `chart`, `chart` needs a chart zone"; chart zones overlaid with their number like other slots
- [ ] 1.4 Built-in deck: add layout "Fred Chart Wide" and its example slide (native column chart, theme colours) to `assets/fred_template.pptx`; regenerate `assets/fred_template.inventory.json` (`make builtin-inventory`): `layout:9`/`slide:265` become one `chart` pattern, the wide slide a second
- Verification: `test_builder_analysis.py` (chart placeholder layout, example chart slide included, small decorative chart untouched, `OBJECT` vs `BODY` capability), `test_labelling.py` (vision `chart` accepted only with a chart zone), `test_builtin_template.py` passes on the regenerated JSON and finds both chart variants

### 2. Plan, validation and assignment

- [ ] 2.1 `plan.py`: `PlanChart` (`type`, `categories`, `series[{name, values}]`, `title`, `unit`) with the coercions of design D1 (aliases, `{name: value}` pairs, numeric text, unit inference, gaps kept with their text, `ignored_fields`); `SlidePlan.chart` before `notes`/`kind`; unknown type → `column`, the type asked kept for the note
- [ ] 2.2 `assign.py`: data validation of design D5 as a slide problem with remedies; `infer_kinds` → `chart` first for a slide with a chart; fit check against chart zones and free chart-capable zones (design D6 room); a chart zone needs a chart; `CLOSE_KINDS["chart"]`; tier-3 refusal with options read from the template (table / figures slide present); charts excluded from D24 splitting and from variety recasting (design D8); tier-2 substitution note
- [ ] 2.3 `tools.py`: catalogue line and schema for `chart` (offered only when the template can host one; words then chars, D22); description sentence "numbers that compare → `chart` with data only"
- Verification: new `test_chart_slides.py` (plan coercion cases, each D5 message, tier 1 > tier 2 > tier 3, no split, variety never recasts a chart, ignored `color` key), `test_assign.py` and `test_build_tool.py` extended

### 3. Rendering

- [ ] 3.1 New `builder/charts.py`, header crediting PR #3058 (Shuigami): type mapping, `CategoryChartData`, legend rule, length guard ported; theme accent `schemeClr` per series / per point; theme body font, size from the zone (10–14 pt); data labels and unit number format per design D4
- [ ] 3.2 `render.py`: the chart's host (chart zone, else free chart-capable zone) replaced by a native chart at its box and drawing-order place; an unfilled chart zone removed; tier-2 and type-fallback notes in the summary
- [ ] 3.3 `checks.py`: no chart frame without its chart part left on a delivered slide
- [ ] 3.4 Preview check: render column, pie, stacked column and area decks on the built-in template through LibreOffice and confirm theme accents, readable labels, no overflow (evidence in `verification.md`)
- Verification: ported #3058 tests (`test_native_chart_slide_adds_editable_chart_with_title`, legend position, category length mismatch) adapted to `test_chart_slides.py`; new: `schemeClr accentN` and no `srgbClr` in the chart XML, chart frame equals the zone box, the saved deck reopens in python-pptx with `has_chart`, the seven types each build

### 4. Changes and summary

- [ ] 4.1 `changes.py`: chart field paths of design D8; `chart` clearable by a kind edit
- [ ] 4.2 Summary (D25): `chart` kind, `other_kind` naming `chart` on tier 2, `chart_type_changed` code (`fill.py` note codes)
- Verification: `test_deck_changes.py` (edit a value, append a category without values → named problem, clear `chart`, kind edit to `bullets` clears `chart`); summary entries asserted in `test_chart_slides.py`

### 5. Frontend

- [ ] 5.1 Regenerate `pptBuilderCapabilityOpenApi.ts` (`make update-ppt-builder-capability-api`): `chart` in `Pattern.kind` and `Zone.role`
- [ ] 5.2 `ppt_builder/types.ts`: `chart` in the kind list; the kind selector offers it only for patterns holding a chart zone
- [ ] 5.3 `ppt_filler/DeckSummaryButton.tsx` and `locales/{en,fr}`: kind label `chart` and note `chart_type_changed`, non-technical wording
- Verification: `tsc`, `prettier`, `eslint`, `vitest` on the `ppt_builder` folder and `DeckSummaryButton.test.tsx`

### 6. Evaluation, docs, close-out

- [ ] 6.1 `eval/prompts.py`: prompts with chartable data (quarterly figures, market shares); metrics: chart used when data given, first-call success, no colour key sent
- [ ] 6.2 Package `README.md` (charts section, #3058 credit); Help Center builder page (fr+en) if one exists; migration note in `docs/swift/ops/migrations/` (impact none, patch)
- [ ] 6.3 Package `make test`, `ruff check` (incl. `--select I`), `ruff format --check`, basedpyright with its baseline; `openspec validate ppt-builder-charts --strict`
- Verification: `verification.md` with test counts, the evidence decks, and what stays unproven (PowerPoint rendering checked by hand only)

## Phase B — the template's own example chart (after the owner has tested phase A)

### 7. Example chart reuse

- [ ] 7.1 `render.py` `_duplicate_slide`: copy a chart zone's chart part with its embedded workbook (and chart style/colour parts when present) under new part names, rewire the frame's `r:id`; any copy failure falls back to the phase A path
- [ ] 7.2 `charts.py`: when the pattern is an example slide whose chart zone's `chart_type` equals the plan's type, `chart.replace_data()` with the plan's data, then only the data-dependent rules (legend presence, data labels, unit number format); extra series beyond the example's get theme accents
- [ ] 7.3 `assign.py`: no change to the choice of slide (the type match only changes how the chart is drawn); `tools.py` summary unchanged
- [ ] 7.4 `checks.py`: the copied chart part is related once and holds the plan's categories and values
- Verification: tests on the built-in example chart (column requested → its own `srgbClr`/formatting kept and values replaced; pie requested → fresh phase A chart), the saved deck reopens with `has_chart` and one workbook per chart; evidence PDF of the built-in chart slide before/after

### 8. Phase B close-out

- [ ] 8.1 `verification.md` phase B section; README update; `openspec validate ppt-builder-charts --strict`; archive after `ppt-builder-capability`
