## Phase A — chart emphasis

### 1. Shared intent rule

- [x] 1.1 `plan.py`: a shared word-to-mode helper (`_named`, en/fr spellings through `lexicon.normalize`, also used by `show`); the unread word kept in the hidden `PlanChart.asked_intents`, carried across a re-validation (design D1)
- [x] 1.2 `fill.py`: `BuildNoteCode` gains `intent_not_shown` (`intent_shown_otherwise` comes with the first fallback, phase B); `BuildNote.field: Optional[str]`; `checks.DeckReport.note` keyed on `(code, field)`
- [x] 1.3 `render.py` `_tell_intent`: records the summary note and the agent note; an identical note on several slides is one line naming them
- [x] 1.4 Frontend `ppt_filler/types.ts` (`field`), `DeckSummaryButton.tsx`, `locales/{en,fr}`: wording per field (`highlight`, `sort`, `stacked_as`) and a generic one for a field the UI does not know yet
- Verification: loose spellings and unread words in `test_chart_intents.py`; two line charts with the same sort note give one "Slides 2, 4" line; `DeckSummaryButton.test.tsx` covers the per-field and generic wording; `tsc`, `prettier`, `eslint`, `vitest`

### 2. Chart sort, highlight, percent stacking

- [x] 2.1 `plan.py` `PlanChart`: `highlight: Optional[str]`, `sort: Optional[Literal["desc","asc","given"]]`, `stacked_as: Optional[Literal["value","percent"]]`, one-line descriptions, after `show`; aliases (`emphasis`, `focus`, `order`, `sort_by`, `stacking`…)
- [x] 2.2 `charts.py`: stable sort of categories with every series (first series, or totals on `stacked_column`); a sorted `bar` fed reversed so the first of the order is on top, an unsorted bar unchanged; sort skipped on `line`/`area` with the note
- [x] 2.3 `charts.py`: highlight resolution (series first when several, else category) and rendering — `accent1`, muted `tx1` with `a:alpha` 35 % / 55 %, each point its own `c:dPt`, bold data label of the highlighted point, line widths (D3); unmatched, several names, multi-series category, one-series line/area category → note
- [x] 2.4 `charts.py`: `stacked_as: percent` → `COLUMN_STACKED_100`, axis `0%`; other types → note (D4)
- [x] 2.5 `changes.py`: `chart.highlight`, `chart.sort`, `chart.stacked_as` paths; `unchanged` compares them (through the plan dump)
- [x] 2.6 `tools.py`: the fields sit in `PlanChart`, offered only with a chart host; one description clause ("to make one category or series stand out, set highlight to its name, never a colour; sort: 'desc' puts the largest first; stacked_as: 'percent' shows a stacked_column as shares of 100 %") and `"chart.highlight"` among the edit examples
- [x] 2.7 Preview evidence on the built-in template through LibreOffice: column and pie/doughnut highlights, two-series line with a highlighted series, sorted bar (largest on top), sorted + highlighted column, 100 % stacked column, the noted cases (see `verification.md`). A dark-background theme is not covered (no such template in the test assets)
- Verification: `test_chart_intents.py` — sort orders (stable ties, totals for stacked, bar reversed, plan kept), `accent1` on the highlighted point / series and `a:alpha` on the others, no `srgbClr`, bold label, each note case, `COLUMN_STACKED_100`, edits of the three paths on the same template slide; existing `test_chart_slides.py` still green

## Phase B — tables and key figures

### 3. Table total row and highlights

- [x] 3.1 `plan.py` `PlanTable`: `total_row: bool = False`, `highlight_row`, `highlight_column` (int or str), coerced (`"yes"`, `"last"` → `true` for `total_row`)
- [x] 3.2 `table_intents.py` (rendered from `render.py`): table style resolution (`a:tableStyleId`, else `tableStyles.xml` `def`); predefined GUID list with each style's accent (new data module); custom style `a:lastRow` / `firstRow` fill read
- [x] 3.3 `render.py` `fill_table`: `lastRow` set or cleared (D6); bold fallback with `intent_shown_otherwise`; highlight row/column resolved against the plan and mapped through the fit, bold + tinted accent, dark-style skip (D7)
- [x] 3.4 `changes.py`: `table.total_row`, `table.highlight_row`, `table.highlight_column`
- [x] 3.5 `tools.py`: the three fields only when the template has a `table` kind
- Verification: `test_table_intents.py` — `lastRow="1"` set on a predefined style, cleared on a template table that had it, bold fallback on a style without `a:lastRow`; row by index and by first-cell text, column by header text, out-of-range → note, header-less template shifts the row; tint references the style's accent (Accent 2 style → `accent2`); preview evidence of a total row and a highlighted row through LibreOffice

### 4. Key-figure trend

- [x] 4.1 `plan.py` `PlanItem.trend: Optional[Literal["up","down","flat"]]`, coerced spellings
- [x] 4.2 `render.py` `_assign_group` / text writing: the glyph run before the figure in the `number` zone, copied run properties at 60 %, thin space; capacity counts it; no number zone → note (D8)
- [x] 4.3 `changes.py`: `items[i].trend`; `tools.py`: `trend` offered only with a number zone in a group (a trend needs a written number: an auto-numbered item is noted)
- Verification: `test_figure_trend.py` — glyph per value, run properties copied (no colour written), fit with the glyph, note on a group without a number zone; preview of the built-in "Fred Key Figures" slide with three trends

## Phase C — slide takeaway

### 5. Analysis and labelling

- [x] 5.1 `lexicon.py`: `TAKEAWAY_NAMES`; `models.py`: `Zone.takeaway: bool = False`
- [x] 5.2 `analysis.py`: takeaway flag from the shape or layout-placeholder name, one per pattern; `ANALYSIS_VERSION` 16 → 17
- [x] 5.3 `labelling.py`: a vision purpose matching the names sets the flag; prompt slot example "key message"
- [x] 5.4 Regenerate `assets/fred_template.inventory.json` (`make builtin-inventory`): "Fred Chart" takeaway zone flagged
- Verification: `test_builder_analysis.py` (named placeholder flagged, unnamed body not, two candidates → first only), `test_labelling.py` (purpose "key message" flags), `test_builtin_template.py` on the regenerated JSON

### 6. Plan, assignment, rendering

Needs `SlidePlan.takeaway` from `ppt-builder-storytelling` (field, checks, notes, `changes` path).

- [x] 6.1 `plan.py` `DeckPlan.show_takeaways: bool = False` (top-level build argument, one schema line, offered only with a takeaway zone, kept from the base by `changes`; the honoured flag goes on each slide as the hidden `takeaway_shown`); `lexicon.py` `SHOW_TAKEAWAY_WORDS` (fr/en), matched through the storytelling change's user-message lexicon helper; the flag without a matching user message ignored with one agent note
- [x] 6.2 `render.py` `_assign_text`: with the flag honoured, the takeaway into the assigned slide's takeaway zone when it fits, bullets no longer fall into that zone then; otherwise (default) today's filling, no note. The filled zone counts for `_fullest` (assignment reads `_assign_text`)
- [x] 6.3 `tools.py` catalogue: `takeaway zone ≤N words` on patterns holding the zone
- Verification: `test_takeaway.py` — default (no flag): built-in chart slide's card filled from the bullets as before and the takeaway in the notes only; flag + "affiche les messages clés" in a user message: a short takeaway in the card; flag without such a message: card as before plus the agent note; a takeaway longer than the card left in the notes only with bullets filling the card; bullets slide without a zone unchanged; edit of `takeaway` refills the card when the flag is honoured

## Phase D — chart target (dropped)

Dropped by the owner on 2026-10-16 (design D5, Owner decisions (2026-10-16)): a target line would be a combo chart, refused for the chart types change; no task left.

## Close-out (each phase, one PR for the whole capability)

- [x] 8.1 `eval/prompts.py`: prompts implying emphasis ("Q3 is our record quarter", "the last line is the total", "revenue up, costs down", "show the key messages on the slides"), each with an edit turn; `run_eval.py` metrics: intents used, and the tool schema size per template beside first-call success (harness only; not run here: it needs a real LLM)
- [x] 8.2 Package `README.md` intent section; migration note `docs/swift/ops/migrations/ppt-builder-capability.md` (item 6: no action; the cleared template `lastRow` and the analysis refresh named); Help Center fr/en (tables, key-figure arrows, key messages on the slides)
- [x] 8.3 Package `make test`, `ruff check` (incl. `--select I`), `ruff format --check`, basedpyright with its baseline; `openspec validate ppt-builder-intent-fields --strict`
- Verification: `verification.md` per phase with test counts, preview evidence and what stays unproven (PowerPoint rendering checked by hand only)
