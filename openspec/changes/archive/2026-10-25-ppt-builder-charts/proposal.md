## Why

Business decks carry numbers, and `ppt_builder` (GitHub issue #2679) cannot show them as a chart: today a template slide holding a chart is excluded (`exclusion_reason="chart"`, its chart part is not copyable), and a `chart` placeholder is ignored by the analysis. The built-in Fred template already ships a "Fred Chart" layout (title, `chart` placeholder, takeaway body) and an example chart slide, both unused.

External PR #3058 (`pptx_generator`, by Shuigami) brought a working chart engine (native python-pptx charts, matplotlib fallbacks), but its decks were judged ugly once tested: the model positioned and styled everything, colours included. `ppt_builder`'s rule stays: **the model writes content, the code picks the design**. Charts must enter as data the model fills and the code places into a zone the template offers, under the existing fit, variety and deck rules.

## What Changes

Two phases in this one change (owner decision, 2026-10-14). **Phase A** is built and tested first; **phase B** stays as tasks until the owner has tested phase A.

Phase A — fresh native charts:

- **New content field `chart`** on a slide of the plan: `{type, categories, series: [{name, values}], title?, unit?}` with `type` in `column | bar | line | pie | doughnut | stacked_column | area`. No colour, position, size, font or style field: the schema has none to fill.
- **New slide kind `chart`** in the closed vocabulary; inferred from a plan slide carrying `chart`.
- **Chart zones in the analysis.** A `chart` placeholder (layout or example slide) and a chart graphic frame covering the main area of an example slide become a zone of role `chart` (the slide is no longer excluded). A large content (`OBJECT`) placeholder is marked `chart_capable`, the fallback place PowerPoint itself offers.
- **Assignment and fit.** A chart goes to a `chart` zone first, else to a free chart-capable content placeholder (a close-kind substitution, reported to the model and in the deck summary), else the tool returns `needs_revision` ("this template has no place for a chart; give the data as a table or as figures"). Never drawn on a free area.
- **Data validation with actionable messages**: one value per category in every series, numbers only (common written forms coerced), caps on categories, series and label length measured from the zone, pie/doughnut rules. Nothing is cut silently.
- **Native, editable charts, theme-styled.** The code inserts a python-pptx chart into the zone's frame; series and pie points reference the theme accents (`schemeClr accent1..6`), text references the theme body font (`+mn-lt`); legend, data labels and number format are decided by the code.
- **Edits** through the existing `changes` operations (`chart`, `chart.type`, `chart.series[1].values[3]`…), the kind-edit clearing rule and `like` unchanged.
- **Summary and preview**: the "What was built" entry shows kind `chart` (or the substituted kind with `chart` asked); new note `chart_type_changed`; the PDF preview renders the native chart; review dialog and kind selector learn `chart`.
- **Built-in template**: a second chart slide, a full-width chart without the takeaway box, is added to `fred_template.pptx`; its stored inventory is regenerated with `make builtin-inventory`.
- **Ported from #3058** (credited in code and README): the chart-type mapping, chart-data construction, legend rule, series-length check and their tests. Not ported: model-chosen colours, generic content-box placement, scatter/bubble/radar, the matplotlib fallbacks.
- `ANALYSIS_VERSION` 11 → 12; the analysis also records an example chart's own type, which phase B reads.

Phase B — the template's own example chart (tasks only, not built now):

- When the chosen template slide is an example slide whose chart has the requested type, the slide is duplicated **with** its chart part and embedded workbook, and the data is swapped with `chart.replace_data()`: the designer's formatting is kept. Any other case falls back to the phase A fresh chart.

Out of scope (deferred): matplotlib picture charts (waterfall, Gantt, funnel, heatmap) — design D7.

## Capabilities

### New Capabilities

- none

### Modified Capabilities

- `ppt-builder`: adds chart content (requirement "Charts fill a chart zone the template offers"). The base requirements live in the in-flight change `ppt-builder-capability`; this change is applied after it and archived after it.

## Impact

- `libs/capabilities/fred-capability-ppt-filler/fred_capability_ppt_filler/builder/`: `models.py` (`chart` role and kind, `Zone.chart_capable`, `Zone.chart_type`), `analysis.py` (chart zones, `ANALYSIS_VERSION`), `labelling.py` (vision vocabulary), `plan.py` (`PlanChart` and coercion), `assign.py` (fit, close kinds, inference, tier-3 refusal), new `charts.py` (validation, room, native chart insertion), `render.py` (chart hosting), `changes.py` (chart paths), `tools.py` (catalogue, schema, description), `fill.py` (`chart_type_changed` note code), `assets/fred_template.pptx` and its regenerated inventory.
- No new dependency: `python-pptx` (with its `XlsxWriter` dependency) already builds native charts; matplotlib is not added.
- Frontend `apps/frontend/src/rework/features/capabilities/ppt_builder/` (kind list, selector), regenerated `pptBuilderCapabilityOpenApi.ts`, `ppt_filler/DeckSummaryButton.tsx` (note wording) and `locales/{en,fr}`.
- Docs: package `README.md`, migration note (impact none: re-analysis is automatic) → patch.
- Tracking: #2679 (credit to #3058).
