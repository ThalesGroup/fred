## Context

`ppt-builder-charts` (D1–D12) gives a plan slide a data-only `chart` (`PlanChart` in `builder/plan.py`), validated by `charts.data_problems` and `charts.fit_problems`, drawn by `charts.draw` (fresh, theme-referenced) or `charts.refill` (phase B, the example chart's own formatting). `ppt-builder-storytelling` D3/D4 adds `story._units`, `story._spread` (on `_SPREAD_TYPES`) and the sourced-figures checks fed by `story.slide_figures`. Everything below reuses those paths; nothing changes for the seven existing types except one alias.

Code facts that shape the design: `_CHART_TYPE_NAMES["stacked bar"]` builds `stacked_column` today; `PlanChart._coerce` maps a chart-level `x` to `categories`; `x_axis`/`y_axis` are in `_CHART_STYLE_KEYS` (set aside as design); `_FROM_XL` maps only the seven types, so an example radar/scatter chart is recorded with no `chart_type`.

## Goals / Non-Goals

**Goals:** `stacked_bar`, `radar`, `scatter`, `bubble` as native, editable, theme-styled charts under the same zone, fit, refusal, edit, summary and storytelling rules; a model that knows when to pick each.

**Non-Goals:** combo charts; picture charts (D7 of `ppt-builder-charts`); trend lines, log axes, error bars; dates or text on a scatter's x axis; any model-facing style field.

## Decisions

### D1. Types and mapping

| Plan type | python-pptx | Data shape | Notes |
|---|---|---|---|
| `stacked_bar` | `BAR_STACKED` (`BAR_STACKED_100` with `stacked_as: percent`) | categories × series | room as `bar` (height-based); `stacked_as` now valid for both stacked types |
| `radar` | `RADAR_MARKERS` | categories × series | lines with markers: a filled radar hides the back series (same reason as `area`) |
| `scatter` | `XY_SCATTER` | points `{x, y}` | markers only, no connecting line |
| `bubble` | `BUBBLE` | points `{x, y, size}` | size represents area, bubble scale reduced so 15 bubbles stay apart |

Aliases (`_CHART_TYPE_NAMES`): `stacked bar`, `horizontal stacked` → `stacked_bar` (behaviour change, was `stacked_column`); `spider`, `web`, `toile`, `araignee` → `radar`; `xy`, `scatter plot`, `nuage de points`, `dispersion`, `correlation` → `scatter`; `bubbles`, `bulles` → `bubble`. `_FROM_XL` learns `BAR_STACKED(_100)`, `RADAR*`, `XY_SCATTER*`, `BUBBLE*`, so `ANALYSIS_VERSION` 14 → 15 (stored analyses refresh in the background; the built-in inventory is regenerated).

### D2. The points shape (scatter, bubble)

```
chart: {type: scatter|bubble, title?, x_title, x_unit?, y_title, unit?,
        size_title? (bubble), size_unit? (bubble),
        series: [{name, points: [{x, y, size?, label?}]}]}
```

- **One `PlanChart`, one more series field.** `PlanSeries.points: List[PlanPoint]` beside `values`; `PlanPoint{x, y, size, label}` reuses the number parser (`"1 200"`, `"45 %"`, `"€3.2"`), keeping unread text as a gap named by validation. `unit` keeps its meaning (the value axis, here y) so existing prompts and edits stay right; x and size get their own `x_unit`/`size_unit`. Units written in the values are inferred per axis, as `_unit_from_values` does for one axis.
- **Coercion** (models write points many ways): `[x, y]` / `[x, y, size]` lists, `{x, y}` objects with aliases (`z`/`r`/`radius`/`weight`/`volume` → `size`, `name` → `label`), parallel lists `{x: [...], y: [...], size: [...]}` at series or chart level (one series; for these two types only, a chart-level `x` is read as x values, not as `categories`), and a series written with `values` plus numeric `categories` turned into points (categories become x). Non-numeric categories with `values` on a scatter are **not** converted: a problem says to use `line` or `column` (D4).
- **Axis titles** are content, not style: `x_title`/`y_title` (aliases `x_label`, `x_axis_title`, `xlabel`… but `x_axis`/`y_axis` objects stay style keys, set aside as today). The code writes `"<title> (<unit>)"` on each axis and the unit into the axis number format. Bubble `size_title` is drawn as the chart caption's second line (`Bubble size: Revenue (M€)`) because PowerPoint has no size legend.
- **Alternative rejected:** a separate `xy_chart` field (second content field to infer kinds from, to clear on kind edits, to document); `x_values` + `values` parallel to series as in #3058's `ChartSpec` (one x list shared by every series, wrong when series have different items, and invites the model to fill `categories` too).

### D3. Validation and caps (added rows to `charts.data_problems`)

| Check | Message (shape) |
|---|---|
| shape matches type | `a 'scatter' chart takes points; series[0] has values over categories 'Q1'… — use type 'line' or 'column', or give points [{x, y}]` / `a 'radar' chart takes categories and values, not points` |
| x, y (and size) are numbers | `chart.series[0].points[3].x 'n/a' is not a number; write a number or drop that point` |
| axis titles (scatter, bubble) | `chart: no x_title; say what the horizontal axis measures ('Price')` |
| bubble sizes > 0 | `chart.series[1].points[2].size is 0; a bubble needs a positive size` |
| size given on scatter / missing on bubble | `points carry size: use type 'bubble'` / `chart.series[0].points[4] has no size` |
| caps | scatter ≤ 50 points, ≥ 3; bubble ≤ 15 points; scatter/bubble ≤ `MAX_SERIES` (4) series; radar 3–8 categories (`radar: 2 criteria; a radar needs 3 to 8 — use 'column' or 'bar'`), ≤ 3 series (the polygons overlap) |
| point labels | `label` ≤ 2 words; shown as data labels when the chart has ≤ 12 points (pending Q2) |

Fit (`charts.fit_problems`): `stacked_bar` uses the `bar` room; radar category labels get a quarter of the plot width, one line; scatter/bubble have no category room, only axis titles (each a line of the plot), series names and title, measured as today. Caps are builder constants, never settings; nothing is cut or rescaled.

### D4. One measure per chart, applied per axis (extends storytelling D3)

- `stacked_bar` and `radar` share one value axis: they keep the rule unchanged and join `_SPREAD_TYPES` (radar is where "price vs. score out of 10" mixes happen).
- `scatter`/`bubble` relate two (three) measures by nature: the rule becomes **one measure per axis**. `story._units` checks the units written in x, in y and in size separately (`x values mix units (€, %)…`); the spread question does not apply (wide ranges are normal on an XY axis), and the required axis titles replace it as the guard that the reader knows what each axis measures. Pending Q1.
- `story.slide_figures` reads x, y and size of every point, so the source spot-check and `illustrative` caption work unchanged. Takeaway rules unchanged.
- Intents: `highlight` names a series (several series) or a point `label`; `sort` is not applied to scatter/bubble/radar (agent note, as for `line`); `show` stays pie/doughnut only.

### D5. Rendering (`charts.draw` / `refill`)

`_data` returns `CategoryChartData`, `XyChartData` or `BubbleChartData` by type. Series markers and fills take `schemeClr accent{i}` (`_colour`), text the theme body font, legend per the existing rule (several series). Axis titles and per-axis number formats are new code in `_axes`; gridlines unchanged. Phase B `refill` works for the new types when the example chart has the same type (`replace_data` accepts XY data); any mismatch falls back to `draw`. Changing `chart.type` across shapes in an edit leaves the data as is, so the re-validation names the shape problem (D3 row 1): no silent conversion.

### D6. Model guidance (`tools.py`, `plan.py` descriptions)

- Type enum description: `stacked_bar (parts of a whole per category, long labels)`, `radar (3–8 criteria compared for 1–3 items)`, `scatter (how two measures relate across items; points {x, y})`, `bubble (scatter plus a third measure as size)`.
- `_guide` adds "two measures per item → scatter (bubble for a third)" and "items scored on several criteria → radar" beside "numbers that compare → chart"; the field line adds `points [{x, y, size, label}], x_title, x_unit, y_title` and the edit paths `chart.series[0].points[2].y`, `chart.x_title`. The catalogue line lists all eleven types.

### D7. Template, evaluation, docs

- Built-in template: no new layout; the existing chart zones take every type. Only the inventory is regenerated for `ANALYSIS_VERSION`.
- `eval/prompts.py`: four prompts (budget split by department → `stacked_bar`; three offers on six criteria → `radar`; price vs. units for ten products → `scatter`; markets by growth, share and revenue → `bubble`) and one edit each; metrics: expected type chosen, first-call success, axis titles present.
- Help Center (fr+en): the type list in `guides/prepare-powerpoint-template.md` (Charts) and the chart sentence of `features/capabilities.md`, non-technical wording.
- Package `README.md` charts section. Migration note: impact none → patch.

## Risks / Trade-offs

- [Small models write points inconsistently] → broad coercion (D2), one named problem per bad point; measured in the eval.
- [Radar and bubble are misread by audiences] → tight caps and guidance; the type is the model's choice, the takeaway check still applies.
- [LibreOffice preview renders radar/bubble differently from PowerPoint] → evidence decks of each type in `verification.md`; the `.pptx` is authoritative.
- [Alias change `stacked bar` → `stacked_bar`] → an existing deck is not rebuilt; only new calls get the horizontal chart, which is what the words say.

## Migration Plan

`ANALYSIS_VERSION` 15, background refresh (D20 of the base change); no setting, table or dependency. Migration note impact none → patch.

## Open Questions for the owner

- **Q1. Two measures on a scatter.** Proposed: a scatter or bubble may show two (three) different measures, one per axis, each axis with one unit and a required title; the "do these values measure the same thing?" question is skipped for them. Is that acceptable as the exception to "one measure per chart"?
- **Q2. Dot names on scatter and bubble.** Proposed: each dot may carry a short name (a product, a country) shown next to it when the chart has 12 dots or fewer, and hidden above that (too crowded). Keep, change the threshold, or never show names?
