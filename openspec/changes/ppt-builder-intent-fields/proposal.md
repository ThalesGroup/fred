## Why

`ppt_builder` (GitHub issue #2679) builds decks whose look comes from the template, but the model has no way to say what a slide is *about*: which bar matters, that the last table row is a total, that a KPI is rising, what the slide's takeaway is. A designer would show each of these; today the deck shows none, and a model that tries (colours, bold) is ignored by design. The owner's rule (2026-10-14): **the model gives data and intent, the code decides the look from the template**. Intent fields express meaning, never style; each is optional with a safe default, a short enumeration or a reference to content already in the plan, validated, editable through `changes`, and never silent.

## What Changes

One cross-cutting rule, then nine optional fields in four phases, all on one branch (each phase built, tested by the owner, then the next; the owner opens a single PR for the whole capability):

- **Rule (all phases).** An intent the template cannot render, or a reference that matches nothing, never blocks the build: the deck is built without it, the agent gets a note with the remedy, the "What was built" summary gets `intent_not_shown` (phase A), or `intent_shown_otherwise` when a fallback rendered it (from phase B, with the first fallback). No field takes a colour, font, size or position.
- **Phase A — chart emphasis** (`charts.py` only, no re-analysis):
  - `chart.sort: desc | asc | given` (default `given`); not on `line`/`area` (time order).
  - `chart.highlight: <category or series name>`: that category (one-series column, bar, stacked column; pie, doughnut) or series (several series) in `accent1`, the rest muted (`tx1` at 35 % / 55 % opacity). A category on a one-series line or area chart is noted, not drawn.
  - `chart.stacked_as: value | percent` (default `value`); `percent` builds a 100 % stacked column; `stacked_column` only.
  - A sorted bar chart draws the first of the sorted order on top (the data is fed in reverse); an unsorted bar chart is unchanged.
- **Phase B — tables and key figures** (render-time detection, no re-analysis):
  - `table.total_row: bool`: the table style's own total-row formatting (`lastRow` flag), else bold.
  - `table.highlight_row` / `table.highlight_column`: an index or the row's first-cell / the column's header text; bold and a light tint of the table style's accent.
  - `items[i].trend: up | down | flat`: a ▲ ▼ ► glyph before the figure, in the figure's own text style; no colour.
- **Phase C — slide takeaway** (re-analysis):
  - the slide's `takeaway` (field owned by `ppt-builder-storytelling`) placed in the template's takeaway zone (shape name or vision purpose) only when the user explicitly asked to show key messages (`show_takeaways`, checked against the user's words) and it fits; by default the zone is filled from the slide's content as before and the takeaway stays in the speaker notes only (owner, 2026-10-15).
  - `Zone.takeaway` flag; `ANALYSIS_VERSION` 12 → 13.
- **Phase D — chart target** (gated on a spike):
  - `chart.target: number | {value, label}`: a dashed reference line built natively (an extra series moved into a line plot sharing the axes: a combo chart, editable in PowerPoint); `column`, `stacked_column`, `line`, `area` only.
- **Edits** through the existing `changes` paths (`chart.highlight`, `table.total_row`, `items[2].trend`…; `takeaway` through `ppt-builder-storytelling`).
- **Schema cost**: each field is one short line, offered only when the template can use it (chart fields with a chart host, table fields with a table slide, `trend` with a number zone in a group).

Out of scope (owner decisions, 2026-10-14): template trend icons, semantic colours, colour of a takeaway box, a takeaway geometry heuristic. The chart `show` field (pie/doughnut label mode) has landed in `ppt-builder-charts` and is not touched.

## Capabilities

### New Capabilities

- none

### Modified Capabilities

- `ppt-builder`: requirements "Intent fields express meaning, never style", "Chart emphasis", "Table and key-figure emphasis", "Slide takeaway". Applied and archived after `ppt-builder-capability` and `ppt-builder-charts`; phase C after `ppt-builder-storytelling` (which owns `takeaway`).

## Impact

- `libs/capabilities/fred-capability-ppt-filler/fred_capability_ppt_filler/builder/`: `plan.py` (fields, coercion), `charts.py` (sort, highlight, percent stacking, target), `render.py` (table emphasis, trend glyph, takeaway zone filling), `analysis.py`/`lexicon.py`/`labelling.py` (takeaway zone, phase C), `models.py` (`Zone.takeaway`), `changes.py` (paths), `tools.py` (schema, catalogue, description); `fill.py` (note codes, `BuildNote.field`), `checks.py` (notes keyed on code and field).
- Frontend: `ppt_filler/types.ts`, `DeckSummaryButton.tsx`, `locales/{en,fr}` (note wording per field); regenerated `pptBuilderCapabilityOpenApi.ts` only if `Zone` is exposed there (phase C).
- No new dependency. Migration note: impact none (re-analysis automatic; existing charts unchanged) → patch.
