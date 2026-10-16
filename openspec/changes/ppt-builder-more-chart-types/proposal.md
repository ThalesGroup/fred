## Why

`ppt_builder` (in-flight change `ppt-builder-charts`) draws seven native chart types, all of one data shape (categories × series). Business decks also need horizontal stacked bars, radar profiles and relations between two measures (scatter, bubble), which today fall back to a column chart with a `chart_type_changed` note. GitHub issue #3136.

## What Changes

- **Four more native types** (owner decision, 2026-10-16): `stacked_bar` (`BAR_STACKED`, `stacked_as: percent` → `BAR_STACKED_100`) and `radar` (`RADAR_MARKERS`) on the existing category shape; `scatter` (`XY_SCATTER`) and `bubble` (`BUBBLE`) on a new **points** shape: `series: [{name, points: [{x, y, size?, label?}]}]` with axis fields `x_title`, `x_unit`, `y_title` (`unit` stays the y unit) and, for bubble, `size_title`/`size_unit`.
- **Validation with actionable messages**, as `ppt-builder-charts` D5: shape matches type (categories ↔ points, named problem, never converted silently except numeric categories into x values), numbers only (same coercion), caps (radar 3–8 categories; scatter ≤ 50 points; bubble ≤ 15 points, sizes > 0), axis titles required on scatter/bubble.
- **One measure per chart, per axis** (storytelling D3 extended): radar and stacked bar follow the existing rule (units and spread); on scatter/bubble each axis (x, y, size) carries one measure with one unit, the spread question does not apply — an owner question.
- **Same rules as every chart**: chart zones and chart-capable placeholders only, theme accents (`schemeClr`), theme body font, code-decided legend, labels and number formats; fit room measured from the zone; edits through `changes` (`chart.series[0].points[2].y`…); phase B example-chart reuse for the new types (`ANALYSIS_VERSION` 15).
- **Model guidance**: the type enum, schema descriptions and the tool guide say when to pick each type; the `"stacked bar"` alias now builds `stacked_bar` (was `stacked_column`).
- **Evaluation prompts** for each new type; **Help Center** (fr+en) chart lists updated.

Out of scope: combo charts (owner refusal, 2026-10-16: python-pptx lacks them and they mix measures); matplotlib picture charts (waterfall, funnel, heatmap, Gantt: `ppt-builder-charts` D7); trend lines; dates on a scatter's x axis.

## Capabilities

### New Capabilities

- none

### Modified Capabilities

- `ppt-builder`: adds requirements "More native chart types" and "Scatter and bubble charts take numeric points". Extends `ppt-builder-charts` and `ppt-builder-storytelling` (both in flight): applied and archived after them.

## Impact

- `libs/capabilities/fred-capability-ppt-filler/fred_capability_ppt_filler/builder/`: `plan.py` (`CHART_TYPES`, `PlanPoint`, `PlanSeries.points`, axis fields, aliases), `charts.py` (mapping, `XyChartData`/`BubbleChartData`, validation, room, axis titles, `_FROM_XL`), `story.py` (per-axis units, figures from points), `changes.py` (point paths), `tools.py` (description, guide), `analysis.py` (`ANALYSIS_VERSION` 15), regenerated built-in inventory; `eval/prompts.py`; tests.
- No new dependency (python-pptx builds all four). Frontend: no new kind; regenerate the client only if the schema enum reaches it; Help Center `guides/prepare-powerpoint-template.md` and `features/capabilities.md` (fr+en).
- Migration note: impact none → patch (a line in the `ppt-builder-capability` note while unreleased, else its own note).
