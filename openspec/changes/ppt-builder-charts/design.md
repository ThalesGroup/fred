## Context

`ppt_builder` (change `ppt-builder-capability`, decisions D1–D25) fills a corporate or built-in template: the model writes per-slide content, `assign.py` picks a template slide under fit and deck rules, `render.py` duplicates and fills it, the tool refuses with `needs_revision` rather than dropping content. Tables entered this way in D14; charts follow the same path.

Facts (verified on `backup/ppt-builder-capability-2026-10-14`):

- `analysis.py` reads a chart graphic frame as record kind `chart`; an example slide whose chart covers ≥ `_MAIN_CONTENT_AREA` is excluded (`exclusion_reason="chart"`), and a `/chart` relationship is not in `COPYABLE_REL_SUFFIXES`, so such a slide is uncopyable anyway. `_placeholder_role` maps `BODY`/`OBJECT` to text and returns `None` for a `CHART` placeholder: the zone is invisible.
- Built-in deck: layout "Fred Chart" (`layout:9`) holds `title` (idx 100), a `chart` placeholder (idx 101, 7.4 M × 4.5 M EMU) and a `takeaway` body (idx 103); it is analysed today as `bullets` with only the narrow takeaway body. Example slide 10 (`slide:265`, "Charts stay native and editable") puts a column chart in that placeholder and is excluded `chart`. Its chart XML hard-codes `srgbClr 4851C3` (the theme's accent1).
- PR #3058 (`fred-capability-pptx-generator`, author Shuigami, Apache-2.0, same repo): `deck_builder._add_native_chart` (mapping to `XL_CHART_TYPE`, `CategoryChartData`/`XyChartData`/`BubbleChartData`, legend rule, length checks), `ChartSpec`/`ChartSeries` in `models.py` (incl. a model-chosen `color`), `chart_render.py` matplotlib fallbacks (heatmap, waterfall, funnel, gantt) with hard-coded colours (`#2e7d32`, `viridis`…), placement in a generic content box (`_take_content_box`).

Owner decisions (2026-10-14): seven native types (D2); tier 2 accepted (D3); a full-width chart slide added to the built-in deck (D10); matplotlib types deferred (D7); two phases in this change, phase B built only after phase A is tested (D11).

## Goals / Non-Goals

**Goals:** a native, editable chart on a template slide built for it, styled by the template's theme, from data the model writes; the same fit/variety/deck rules and actionable refusals as every other kind; edits through `changes`; later (phase B), the template's own example chart reused with its formatting.

**Non-Goals:** chart types beyond the seven (scatter, bubble, radar, stacked bar, combo, waterfall, funnel, heatmap, gantt); image charts; a second chart per slide; charts inside `items`/cards; any model-facing style field.

## Decisions

### D1. Chart content in the plan: data only

`SlidePlan.chart: Optional[PlanChart]`, placed before `notes` and `kind` (content first, D7 of the base change):

```
chart: {type: column|bar|line|pie|doughnut|stacked_column|area, categories: [str],
        series: [{name: str, values: [number]}], title?: str, unit?: str}
```

- Coercion (as `PlanTable`, D14): aliases (`chart_type`/`kind`→`type`, `labels`/`x`→`categories`, `data`→`series`, a bare `values` list → one series named after the chart title or `""`); a series given as `{name: value}` pairs is read as categories + one series; values written as text are parsed (`"12,5"`, `"1 200"`, `"45 %"`, `"€3.2"`), never rescaled: when every text value carries the same unit (`%`, `€`, `M€`…) and no `unit` is given, it becomes the unit; a value that does not read as a number is kept as a gap with the text sent, so validation names it (D5); unknown keys become `ignored_fields` (D15: no silent loss).
- No `color`, `style`, `legend`, `position`, `size`, `font` field. #3058's `ChartSeries.color` is not ported: it is exactly the model-does-design path the owner rejected. Such a key sent anyway is not content: it is set aside (`style_fields`) and named in the delivery note, never applied and never a revision.
- `title` is the chart's own caption (e.g. "Revenue by region"), not the slide title; `unit` labels the values (D4).
- Alternative rejected: reusing #3058's `ChartSpec` as is (carries `color`, `gantt_tasks`, `x_values`, `sizes` the slice does not support; each unused field invites the model to fill it).

### D2. Seven native types

`column`, `bar`, `line`, `pie`, `doughnut`, `stacked_column`, `area` → `XL_CHART_TYPE.COLUMN_CLUSTERED`, `BAR_CLUSTERED`, `LINE_MARKERS`, `PIE`, `DOUGHNUT`, `COLUMN_STACKED`, `AREA`. They share one data shape (categories × series), cover most business decks, and render in both PowerPoint and LibreOffice (the preview). Common spellings are read (`histogram`→`column`, `donut`→`doughnut`, `stacked`→`stacked_column`, `line chart`→`line`…). An unknown `type` is built as `column` and the delivery notes it (`Slide 4: chart type 'radar' is not offered; built as 'column'.`, summary code `chart_type_changed`) — the content is kept, only the form changes. Scatter/bubble need another data shape (x values), radar/stacked bar confuse small models for little gain: later, on demand.

### D3. Where a chart can go: three tiers, never a drawn area

1. **Chart zone** (role `chart`): a `CHART` placeholder on a layout or example slide; or, on an example slide, the one chart graphic frame covering ≥ `_MAIN_CONTENT_AREA` (today an exclusion). The zone stores its box and the example chart's type (`chart_type`, in the plan's vocabulary when it maps to one: read by phase B, D11). The pattern's kind is `chart` whenever it holds a chart zone (rules, then vision, D2 of the base change; vision compatibility: `chart` needs a chart zone, a chart zone needs `chart`). The slide is no longer excluded for that chart; its `/chart` relationship is accepted (the duplicated frame is replaced by the renderer, D4). A slide with two or more such charts stays excluded `chart`; a small chart that is not a zone keeps the slide uncopyable.
2. **Chart-capable content placeholder:** an `OBJECT` (content) placeholder — not `BODY`, which PowerPoint reserves for text — covering ≥ 25 % of the slide (`_CHART_MIN_AREA`) gets `Zone.chart_capable = True`. It keeps its text role; it hosts a chart only when the slide puts no text in it. This is PowerPoint's own "insert chart" place on a "Title and Content" layout, so most corporate templates without a chart slide still host one (owner decision, 2026-10-14).
3. **None:** the slide is a `needs_revision` problem (D21 lead of the base change): `chart: this template has no slide for a chart`, options `give the data as a table` (when the template has a table slide), `give up to N key numbers as items of a 'figures' slide` (when it has one and the chart has ≤ N values), `keep the key numbers as bullets`. Never turned into a table or figures by the code (same rule as D14 for tables).

`CLOSE_KINDS["chart"] = ("bullets", "two_columns", "image_text")`, restricted by the fit check to patterns holding a chart-capable zone the slide leaves free. With no kind asked, a slide carrying `chart` infers `chart` then the same three. A chart on tier 2 is a substitution, named in the success note and in the summary (`other_kind` with kind `chart`, D25). Charts are never split (D24): cutting a series over two slides changes what it says; too many categories is a fit problem (D6). A pattern holding a chart zone needs a chart: a slide without one does not fit it (as a table zone needs a table).

Alternatives rejected: placing the chart in any free area (the #3058 path: the code invents a layout); treating every body placeholder as chart-capable (a `BODY` placeholder is a text frame, often narrow; it gave the "takeaway" box of the Fred Chart layout as a candidate).

### D4. Rendering: a fresh native chart in the zone's frame, theme-referenced

New module `builder/charts.py`, called by `render.py` for a `chart` zone or a chart-capable zone holding the chart:

- **Placement**: `shapes.add_chart` at the zone shape's box, the new frame put back at the replaced shape's place in the drawing order, the replaced shape (chart placeholder, content placeholder, or the duplicated example frame whose chart part was not copied) removed. One path for the three hosts.
- **Colours from the theme, never literal:** each series (column, bar, stacked column, area: fill; line: line and markers) gets `schemeClr accent{(i mod 6) + 1}`; pie/doughnut points get `accent1..accentN`. Literal colours would survive a template switch and break the "theme restyles it" promise; leaving fills unset relies on the reader's default chart style, and LibreOffice (our preview) does not apply the theme palette the way PowerPoint does — the explicit reference is read the same by both. Gridlines and text use `tx1` with a luminance offset, also a theme reference.
- **Text:** the chart-wide text references the theme body font (`+mn-lt`, as the template's own example chart does); one size for axis, legend and data labels: two thirds of the zone's font size (a chart zone stores the presentation's default text size), between 10 and 14 pt.
- **Code-decided presentation**, adapted from #3058: legend at the bottom, outside the plot, when several series or a pie/doughnut, none otherwise; data labels on pie/doughnut (percentages) and on a single-series column/bar with ≤ 8 categories (values); light value-axis gridlines; `chart.title` as the chart's title when given, none otherwise (an untitled single-series chart would show the series name); `unit` in the value-axis and data-label number format (`#,##0.#" M€"`, `0" %"`), decimals as the data has them (≤ 2).
- **Credit:** the module header says it is adapted from `fred-capability-pptx-generator`, by Shuigami (the PR number stays in the README and the commits: no issue numbers in code); the type mapping, `CategoryChartData` construction, legend rule and length check are ported, the rest is new.

### D5. Validation: the plan is checked before assignment

A chart slide is a `needs_revision` problem, all problems listed at once, each with what, why and a remedy (message rule, D21):

| Check | Message (shape) |
|---|---|
| at least one series and one category | `chart: no data; give categories and at least one series` |
| every series has one value per category | `chart.series[1] 'Costs' has 4 values for 5 categories` |
| values are finite numbers | `chart.series[0].values[2] 'n/a' is not a number; use a number or drop that category` |
| pie/doughnut: one series, values ≥ 0, not all 0 | `a 'pie' chart shows one series; keep one, or use 'column'` |
| series ≤ 4 (`_MAX_SERIES`) | `chart: 6 series; at most 4 stay readable` |
| pie/doughnut categories ≤ 6 (`_MAX_SLICES`) | `group the smallest as 'Other'` |
| category count ≤ the zone's room (D6) | `chart: 14 categories; this chart holds 9` |
| category labels, series names, title within room (D6, words first, D22) | `chart.categories[3] is 31 chars; ≤2 words (≈15 chars)` |

Data checks (rows 1–6) do not depend on the template slide; room checks (rows 7–8) are misfits of each candidate. Caps are constants of the builder, not settings. Values are never rounded or rescaled by the code.

### D6. Fit: the room is measured from the zone

At analysis, a chart zone (or chart-capable zone) stores its box; at fit time the room follows from the box and the chart font (D4) with `text_metrics`: the plot takes 85 % of the frame's width and 75 % of its height; categories ≤ plot width ÷ 3 em (column, stacked column, line, area), plot height ÷ 2.2 lines (bar), capped at 12 (24 for line and area); category label room = the width per category, 2 lines (column family, line, area), 40 % of the plot width, 2 lines (bar), a third of the plot width, 1 line (pie/doughnut legend); series names share the legend line; the title holds one line of the frame. The catalogue quotes the room in words then characters (D20, D22): `chart (column, bar, line, pie, doughnut, stacked_column, area) categories max 12, labels ≤2 words (≈15 chars), series max 4`. Variants of kind `chart` are distinct when their zones differ (chart only, chart + takeaway body…); a chart + `bullets` slide needs a variant with a body beside the chart (the takeaway), else the bullets are a "no place" problem with the usual options.

### D7. Matplotlib fallbacks: not in this change (owner decision, 2026-10-14)

Waterfall, funnel, heatmap and Gantt as pictures are deferred to a later change, if a need is shown:

- they are images: not editable, the opposite of the "native first" requirement, and invisible to the after-render text checks;
- #3058's renderers hard-code colours and a `viridis` colormap; making them follow the theme needs theme-colour extraction and font availability in the pod — a slice of its own;
- they add `matplotlib` (and its build footprint) to the package and the fred-agents image, for types with low demand;
- Gantt and funnel overlap the template's own `timeline` and `process` slides, which `ppt_builder` already fills with the designer's look;
- a later change may prefer native constructions (waterfall as a stacked column with an invisible base series) over pictures.

### D8. Edits, variety, deck rules

- `changes` paths extend the existing grammar (D23): `chart` (whole, or null to clear), `chart.type`, `chart.title`, `chart.unit`, `chart.categories[i]`, `chart.series[j]`, `chart.series[j].name`, `chart.series[j].values[i]`; null removes a list element, index = length appends. After the edit the whole chart is re-validated (D5): adding a category without its values is a named problem. `kind` edits, `like`, the design pin (`built_on`) and identical-call refusal are unchanged; the kind-edit clearing rule now also clears `chart` when the new kind has no place for it.
- `chart` is a non-structural kind: reuse cost and max uses apply to its template slides. The variety ask (D15–D17) never proposes recasting a chart slide into another kind (its data has one natural form) and never proposes `chart` as an alternative for text slides; it may offer another `chart` variant.
- Inference: a slide with `chart` infers `chart` first. Cover/closing rules unchanged.

### D9. Summary, preview, review

- "What was built" (D25): the entry's `kind` is `chart` (or the substituted kind on tier 2, with an `other_kind` note naming `chart`); new note code `chart_type_changed` (D2's fallback), its `kind` carrying the type asked. No new code for refusals (nothing is built).
- Preview: LibreOffice renders the native chart into the PDF; no frontend change beyond the kind label. The review thumbnails (patterns deck, never delivered) show an example slide's own chart by sharing its chart part.
- Tool description: `chart {type, categories, series [{name, values}], title, unit}` among the slide fields, "numbers that compare across categories or over time → chart" in the guide, `chart.series[0].values[2]` among the edit paths, each only when the template can host a chart; with no chart slide, the catalogue adds "or a chart in place of the bullets" to the chart-capable variants.
- Review dialog and kind selector: `chart` added to `SlideKind` (regenerated client) and the fr/en labels; the selector offers `chart` only on a pattern holding a chart zone (the same compatibility rule as vision).

### D10. Built-in template (owner decision, 2026-10-14)

Re-analysis turns `layout:9` and `slide:265` into one `chart` pattern (the example slide stands for its layout, D2.1 of the base change) with the takeaway body. A second chart design is added to `fred_template.pptx`: a layout "Fred Chart Wide" (title + chart placeholder across the content width, no takeaway box), inserted right after "Fred Chart", and an example slide on it right after slide 10, holding a native column chart in theme colours. A chart without commentary then never leaves the takeaway box empty: the empty takeaway costs the narrow variant a fit point, so the wide one wins. The deck is edited by a one-off python-pptx script (layout part cloned, example chart inserted through `charts.py`), never by hand in the generated inventory; `make builtin-inventory` regenerates the JSON and the inventory test pins it. Bare layouts after "Fred Chart" shift by one index; a stored `built_on` naming one of them falls back to the normal choice (the design pin only holds while it fits).

### D11. Phase B: the template's own example chart (tasks only until phase A is tested)

When the chosen pattern is an example slide whose chart zone's `chart_type` equals the requested type, the renderer keeps the designer's chart: `_duplicate_slide` copies the chart part with its embedded workbook (and its style/colour parts when present) under new part names, rewires the frame's `r:id`, and the renderer calls `chart.replace_data()` with the plan's data, then applies only the data-dependent rules (legend presence, data labels count, number format with `unit`); colours and fonts stay the designer's. Any other case (layout, chart-capable placeholder, another type, a chart part that does not copy cleanly) falls back to the phase A fresh chart. `replace_data` keeps per-series formatting by index: a plan with more series than the example gets theme accents for the extra ones. The analysis already records `chart_type` (D3), so phase B needs no further `ANALYSIS_VERSION` bump.

## Risks / Trade-offs

- [LibreOffice preview differs from PowerPoint on chart styling] → explicit `schemeClr` fills; a preview check in verification; the `.pptx` stays authoritative.
- [Tier 2 puts charts on plain content slides of templates with a chart slide elsewhere] → tier 1 always ranks first; tier 2 is a reported substitution.
- [Small models write numbers as prose] → coercion of common written forms, then a named `needs_revision` per bad cell; measured in the eval (task 6).
- [Room heuristics for categories are rough] → constants in one place, tuned on the built-in and reference templates; a too-tight room only costs a revision, never a cut.
- [`area` with several series hides the back series] → series drawn in the order given; the type hint tells the model area suits one or two series.
- [Phase B chart-part cloning is fragile across PowerPoint versions] → strict fallback to phase A on any copy failure; phase B lands only after the owner tested phase A.

## Migration Plan

`ANALYSIS_VERSION` 12: stored analyses are refreshed in the background when first seen (D20 mechanism); no config shape change for authors, no new setting, no dependency. Migration note impact none → patch.

## Open Questions

None: Q1–Q5 of the draft were settled by the owner on 2026-10-14 (D2, D3, D7, D10, D11).
