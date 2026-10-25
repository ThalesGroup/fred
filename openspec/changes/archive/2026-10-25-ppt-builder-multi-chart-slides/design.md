## Context

Observed in code (branch `feat/ppt-builder-capability`, `builder/`):

- `analysis.py` step 4c makes a chart zone only when the slide holds exactly one top-level, non-`keep` chart ≥ `_MAIN_CONTENT_AREA` (0.15) and no chart placeholder already made one. `_apply_exclusions` then excludes the slide as `chart` when an unheld chart/table ≥ 0.15 remains, and as `unsupported_parts` when a relationship other than the held charts' parts cannot be copied. Two 24 % charts hit the first rule; four 9.3 % charts hit the second.
- `_chart_zones` stores each chart zone's room (`max_lines`, `chars_per_line`, `font_pt`) and the example's `chart_type`; it already loops over every chart zone.
- `render.chart_host` returns one host (first chart zone in `_reading_order`, else a free chart-capable placeholder); `_fill_chart` fills it (`charts.refill` when `host.chart_type == chart.type`, else `charts.draw`) and removes every other chart zone. `checks.settle_charts` already pairs chart frames and parts one to one, whatever their number.
- `assign.py` checks one chart against one host (`charts.fit_problems`), requires a `chart` on a slide showing a chart zone, and builds the "no place" advice (`_chartless`, `_chart_options`).
- `story.check` runs `_units`/`_spread` on the slide's one chart; `slide_figures` reads its values. `changes.py` validates paths with `_PATH` and a per-field shape table (`"chart": "chart"`).
- `tools.py` hides `chart` from the schema when the template has no chart host, and `catalogue` prints one `chart_summary` per chart zone.

Rules reused, not restated: theme colours and fonts, validation and fit messages, phase B example reuse (`ppt-builder-charts`); the eleven types and points shape (`ppt-builder-more-chart-types`); one measure per chart, takeaway, source (`ppt-builder-storytelling`).

## Goals / Non-Goals

**Goals:** the owner's 2-chart and 4-chart example slides are analysed as chart slides and filled frame by frame from the plan; a one-chart plan behaves exactly as today; every refusal names the chart (`charts[i]`) and the fix.

**Non-Goals:** charts drawn in free areas or a layout computed by the tool; combo charts; charts in `columns`/`items`; more than four charts per slide; a chart placeholder plus free chart frames on one slide (stays as today: the placeholder holds the chart, free main charts exclude the slide).

## Decisions

### D1. Analysis: every eligible chart frame is a zone

Step 4c keeps every chart frame that is top-level (`len(path) == 1`), not a placeholder, not `keep`, and ≥ `_GRID_CHART_AREA` = 0.05, provided none of the slide's chart frames fails those tests and there are at most `MAX_CHARTS_PER_SLIDE` = 4. Otherwise no chart zone is made and `_apply_exclusions` excludes as today. Zones are appended in `_reading_order` (bands of 150 per mille, then x), the same order the renderer and the catalogue use, so `charts[0]` is top-left. `_chart_zones` already sets each zone's room and example type. A frame below 0.05 stays unheld, so its part still triggers `unsupported_parts`: a decoration chart must be declared `keep` (existing naming rule).

Alternatives: keep 0.15 for one chart and 0.05 only for several (rejected: one threshold is simpler and a lone 6 % chart is still a deliberate example chart); infer "grid" by equal sizes (rejected: a big chart beside a small one is a valid design).

### D2. Plan schema: `charts` beside `chart`

`SlidePlan.charts: List[PlanChart]`, placed right after `chart`. A helper `slide_charts(slide)` returns `charts` or `[chart]` (with content), and every reader (assign, render, story, notes, changes, tools) goes through it. Both sent → a `needs_revision` problem ("send `chart` for one chart or `charts` for several, not both"). The schema shows `charts` only when the inventory has a slide with ≥ 2 chart zones, like `chart` is hidden without a host.

Alternatives: `chart` accepting a list (rejected: a union type confuses models and breaks the existing `chart.series…` edit paths); `columns[i].chart` (rejected: columns are text zones, the example slides have none, and the chart's place would depend on text pairing).

### D3. Assignment: exact count

A pattern's chart capacity is its number of chart zones (or 1 for a free chart-capable placeholder). A slide with k charts fits only a pattern with exactly k; anything else is a misfit, so the existing "fewest problems, then cost" ranking applies unchanged. The fit check runs `charts.fit_problems(zone_i, chart_i)` per pair, each reason prefixed `charts[i]`. When no offered pattern has k, `_chartless` becomes "no slide with k charts" and the advice lists the offered counts, then: split into slides of the offered counts, merge or drop charts, or (k = 1 case unchanged) the existing table/figures/bullets options.

Alternative: k charts on a slide with more frames, removing the extra frames (the owner principle "fewest empty zones" would rank it last). Rejected by default because the removed frame leaves a visible hole in a designed grid; see Owner decision 1.

### D4. Titles, units, takeaway

Each chart keeps its own `title`, `unit`, axis fields and type; `story._units` and `_spread` run per chart. With k ≥ 2 a missing `title` is a hard problem (a reader cannot tell the charts apart; the slide title cannot name two measures). The slide keeps one `takeaway` (the charts support it) and one `source` covering all figures; `slide_figures` reads every chart. The illustrative caption (`notes.caption`) is applied to each chart.

Per-chart heading boxes: when a free text box sits directly above a chart frame (same column band, gap ≤ `_PAIR_GAP`), analysis pairs it with that chart and the renderer writes `charts[i].title` there instead of inside the chart; otherwise the title goes in the chart as today. See Owner decision 3.

### D5. Rendering

`chart_host` becomes `chart_hosts(pattern, text, k)` returning the k zones in reading order (k = 1: today's result). `_fill_chart` loops over pairs: refill the example when that frame's `chart_type` matches the chart's type, else draw in the frame's place; unmatched chart zones are removed as today (none with D3). Every renderer note (`_tell`, `_tell_axes`, `_tell_labels`, intent notes, `chart_type_changed`) says "Slide N, chart i" when k ≥ 2.

### D6. Edits

`_SLIDE_KEYS` and the shape table gain `"charts": ("list", "chart")`, so `charts[i].…` paths reuse every `chart` sub-path (`series[j].values[k]`, `points`, `type`, `title`…). `chart.…` on a multi-chart slide is refused with "this slide has k charts: edit `charts[i]`". Replacing `charts` with a list of another length re-assigns the slide (as a `kind` change does); if no pattern has that count, D3's refusal applies.

### D7. After-render check

`checks.py` counts native chart frames with a resolvable part on each delivered slide and compares with the plan's chart count; a difference is a `needs_revision` internal error, never a silent loss. The existing "no `srgbClr`" assertion runs on every chart part.

### D8. Model guidance

`chart_summary` for a pattern with several zones prints `charts×k (types…): categories max …` using the smallest zone's room. The tool guide adds one pair: "two to four related measures side by side, one per chart → a slide with `charts` (only the counts the catalogue lists)". Field description of `charts`: "Several charts on one slide, in reading order; only on a slide the catalogue lists with `charts×N`, exactly N charts, each with a title."

### D9. Version, docs, evaluation

`ANALYSIS_VERSION` 16 and `make builtin-inventory`. Help Center fr+en `guides/prepare-powerpoint-template.md`: a slide may hold up to four example charts, each at least 1/20 of the slide, all filled; package README chart paragraph; migration-note line (impact none, patch). `eval/prompts.py`: `charts_pair` (revenue and margin by region), `charts_grid` (four KPIs over quarters), an edit on `charts[1]`, metrics: multi-chart slide chosen, first-call success, titles present.

## Risks / Trade-offs

- [Small frames are cramped] → room is measured per frame (`fit_problems`), so a 9.3 % chart refuses long labels with its own message rather than overflowing.
- [Models send three charts to a 2/4 template] → the refusal lists the offered counts; evaluation measures first-call success.
- [Re-analysis changes which slides are offered] → slides newly offered are only chosen for `charts` plans, so one-chart decks are unchanged; `ANALYSIS_VERSION` makes it automatic.
- [Pairing heading boxes misfires on unusual layouts] → pairing is limited to a box directly above one frame; otherwise the title stays in the chart.

## Owner decisions (2026-10-16)

1. **Chart count with no matching slide:** the tool asks the assistant to change its slide (split or merge); it never leaves a gap in a designed grid. The owner adds a 3-chart example slide to the template, so 2, 3 and 4 charts are covered there (template-first).
2. **Smallest chart filled:** at least 1/20 of the slide, at most four charts per slide; anything smaller keeps the slide out, as today.
3. **Text box right above a chart:** the chart's title goes in that box, not again inside the chart.
4. **Key message:** one takeaway per slide; each chart has its own title.

## Size

Medium: about 3 to 4 days including tests and evidence. Most work is plumbing one chart into a list through assign, render, story and changes; analysis and the after-render check are small.
