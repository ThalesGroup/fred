## Context

`ppt_builder` (change `ppt-builder-capability`, D1–D26; charts in `ppt-builder-charts`, D1–D11) fills a template: the model writes content, `assign.py` picks the slide, `render.py`/`charts.py` draw it, problems come back as `needs_revision`, and each rendered slide gets a "What was built" entry with note codes (D25). Charts already refuse design keys (`PlanChart.style_fields`, set aside and named in the delivery note). The chart `show: share | value | both` field (pie/doughnut labels, an unknown word a `needs_revision`) has landed in `ppt-builder-charts`; this change does not touch it, and its intents follow `show`'s pattern (a `Literal` with loose spellings, the unread word kept in a hidden field for the note). The per-section variety rule and `repeat_layout` (also landed) do not interact with intents.

Facts (drafted at `4d0057e41`; phase A facts re-checked at `25727177d`, phase B–D facts to re-check when each phase starts):

- `charts.py` colours series `accent1..6` in order (`_colour`), labels single-series column/bar with ≤ 8 categories and pies in percent (`_labels`), and draws gridlines with `tx1` at brightness 0.85. `XL_TYPES` has `stacked_column` → `COLUMN_STACKED`; no 100 % variant. A `bar` chart lists its first category at the bottom (python-pptx default, `c:orientation minMax`). `python-pptx >= 1.0.2` (axis `reverse_order` available).
- `render.fill_table` keeps the duplicated frame's `a:tblPr` as is: its `firstRow`/`bandRow`/`lastRow` flags and `tableStyleId` come from the template. A template table with `lastRow="1"` therefore styles the last data row as a total whatever the data. The built-in deck's `tableStyles.xml` default is `{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}` (Medium Style 2 – Accent 1); the reference corporate template (Paintress, D14) uses Medium Style 2 – Accent 2. Predefined styles are referenced by GUID and not defined in the file.
- Key figures: `_assign_group` writes `item.number` (or an auto number) into a `number` zone; the built-in "Fred Key Figures" layout has `statN_value` / `statN_label` placeholders over filled cards. No icon or arrow shape exists in the built-in deck.
- Takeaway: the built-in "Fred Chart" layout has a body placeholder named `takeaway` (prompt "Key takeaway", idx 103) drawn over a filled card shape; today it is an ordinary `body` zone filled from `bullets`. Nothing in `models.py`/`lexicon.py` knows the word. Vision labelling already returns a free-text purpose per slot (`Zone.purpose`).
- `changes.py` path grammar (`[a-z_]+(\[n\])*` segments, typed by `_FIELDS`) accepts new leaf names once declared; `CLEARABLE` lists what a kind edit can clear.
- The theme has no semantic colours: OOXML defines `dk1/lt1/dk2/lt2/accent1..6/hlink`; the built-in theme's `accent5` happens to be green (`2C6A41`), `accent6` orange — not "good"/"bad".
- `BuildNote` (`fill.py`) is `{code, count?, kind?}`; the frontend mirrors it in `ppt_filler/types.ts` (a chat-part type, not generated).

## Goals / Non-Goals

**Goals:** let the model say what matters on a slide, in a vocabulary a weak model can ignore or fill; render each intent from the template (theme colours, table style, the figure's own text, a zone the template designed), never from model-chosen style; never lose an intent silently.

**Non-Goals:** any colour, font, size or position field; free-text styling ("make it red"); semantic up/down colours; template icon banks; annotations or callouts drawn on charts; a second takeaway per slide; highlight of several categories at once.

## Decisions

### D1. One rule for every intent field

- **Shape.** Optional, default = today's rendering. Enumerations are short and coerced from common spellings (en/fr: `descending`, `décroissant`, `largest first` → `desc`; `hausse`, `increase`, `↑`, `+` → `up`; `stable` → `flat`); references name content already in the plan (a category, a series name, a header, a row's first cell, an index), compared after `lexicon.normalize`.
- **Validation never blocks.** An intent is not content: a value that reads as nothing, a reference that matches nothing, or a template that cannot render it leaves the deck built without that intent. This differs on purpose from content (D8/D21 of the base change: refuse rather than drop), because a revision round spent on emphasis costs more than the emphasis is worth, and a weak model would loop on it.
- **Never silent.** Each such case sends one agent note with the remedy (`Slide 4: highlight 'Nord' matches no category (Q1, Q2, Q3, Q4); built without highlight. To set it, edit chart.highlight to one of those.`) and records a summary note on the slide: `intent_not_shown` (not rendered) or `intent_shown_otherwise` (rendered by a fallback: total row in bold only). `BuildNote` gains `field: Optional[str]` (`highlight`, `sort`, `stacked_as`, `target`, `total_row`, `highlight_row`, `highlight_column`, `trend`); `DeckReport.note` merges on `(code, field)`; the frontend words each pair for a non-technical reader, with a generic wording for a field it does not know yet. An identical agent note on several slides is one line naming them (`Slides 2, 4: …`). Phase A adds `intent_not_shown` only; `intent_shown_otherwise` arrives with the first fallback (phase B).
- **Not style.** Keys that are style (`highlight_color`, `bold`, `emphasis_style`…) stay in `style_fields` (charts) or `ignored_fields` (elsewhere) as today; the intent fields never accept a colour value (`highlight: "red"` matches no category → `intent_not_shown`).
- **Plan keeps what the model wrote.** Sorting, matching and fallbacks happen at render; the plan (and so every `changes` path and index) stays in the order given.
- **Schema.** One-line descriptions; each field offered only when the template can use it (`_schema_for`): chart fields with a chart host, table fields with a `table` kind, `trend` when a repeat group holds a `number` zone. `takeaway` is offered by `ppt-builder-storytelling` on every slide (D9).

### D2. `chart.sort: desc | asc | given`

Default `given`. Reorders categories and every series' values together, stably, by the first series' values (one series, clustered types) or by the category totals (`stacked_column`). Not applied to `line` and `area` (their categories are usually time): `intent_not_shown` with "a line chart keeps its categories' order". `pie`/`doughnut`: sorted slices start at 12 o'clock clockwise.

Bar order: a `bar` chart draws its first category at the bottom. With `sort` set, the sorted order is fed to the chart reversed, so the first of the order (the largest for `desc`) is on top; the axis is not touched. Without `sort` (or `given`), a bar chart is drawn exactly as before: no existing chart changes (owner request, 2026-10-14; the draft's `reverse_order` on every bar chart was dropped). Effort **S**.

### D3. `chart.highlight: <category or series name>`

One reference, matched against series names first when the chart has several series, else against categories.

| Chart | Match | Rendering |
|---|---|---|
| one series (column, bar, stacked column), pie, doughnut | a category | that point (bar, slice) in `accent1`; other points muted, each with its own `c:dPt`; on labelled charts the point's data label bold (a series-level `c:dLbls` repeating the plot's labels plus one bold `c:dLbl`; on a doughnut the shared labels turn `tx1` and the highlighted one `bg1`) |
| one series line or area | a category | not rendered: `intent_not_shown` ("use type 'column'"). LibreOffice ignores a point's own marker colour and an area has no separate points |
| several series (column, bar, line, stacked column, area) | a series | that series in `accent1` (line 3 pt), others muted (line 1.5 pt, no markers) |
| several series | a category only | not rendered: `intent_not_shown` ("highlight a series, or keep one series") |

**Muted** = `tx1` with `a:alpha` 35 % (preview-checked: LibreOffice renders chart `a:alpha`, but lays a series-level opacity over every point, so a highlighted category colours each point on its own rather than muting the series): on a light background it reads as a mid grey, on a dark one as a dim light grey, so it stays below the accent on any theme (a fixed brightness on `tx1`, as the gridlines use, turns *brighter* than the accent on a dark theme). Several muted series or slices alternate 35 % and 55 % (muted bars of one series all take 35 %); muted slices keep the existing `bg1` edge. Known limit: on a highlighted pie with more than three slices, the legend tells the muted slices apart only by two tones; the highlighted slice stays unambiguous. The highlight is `accent1`, the first colour the theme gives a chart; no other accent appears on a highlighted chart. Effort **M**.

### D4. `chart.stacked_as: value | percent`

Default `value`. `percent` → `XL_CHART_TYPE.COLUMN_STACKED_100`, value axis `0%`, unit ignored for the axis (the series' `unit` stays in the workbook format). Only on `stacked_column`; on any other type `intent_not_shown` ("percent stacking needs type stacked_column"). Not folded into `type` (a new type value would double the type list a weak model reads) — see Q4 for the relation to `show`. Effort **S**.

### D5. `chart.target: number | {value, label?}` (phase D)

A reference value drawn as a horizontal dashed line across the plot.

Options studied (python-pptx 1.0, native charts):

1. **Combo chart, chosen.** The target is added to `CategoryChartData` as one more series (constant value per category), so the embedded workbook holds it and "Edit Data" in PowerPoint keeps it. After `add_chart`, its `c:ser` is moved out of the `c:barChart`/`c:areaChart` into a new `c:lineChart` (grouping `standard`, the same two `c:axId`), inserted after the first plot in `c:plotArea` — PowerPoint's own "Combo: clustered column – line". On a `line` chart it stays in the `c:lineChart`. Styled by the code: `tx1` at 75 % opacity, 1.5 pt, `prstDash dash`, no markers, not stacked, never sorted or highlighted. One data label on its last point: `label` + the value in the chart's number format (`Target 15 M€`, or `15 M€` without a label), so no legend appears just for it; in a chart that already has a legend its entry is deleted (`c:legendEntry/c:delete`).
2. Line shape drawn over the plot area: rejected. The plot area's position is computed by the reader (PowerPoint and LibreOffice differ), so the line lands off the value; it detaches when the chart is resized or edited.
3. Error bars or high-low lines on a hidden series: rejected; unreadable in "Edit Data" and inconsistently rendered by LibreOffice.

Limits: a line joins the category centres, so it stops half a category short of the plot edges (accepted; PowerPoint's own combo does the same). Not on `bar` (its value axis is horizontal: a line plot would run along the categories), `pie`, `doughnut`, nor with `stacked_as: percent` (a value target on a percent axis has no meaning): `intent_not_shown`. The value axis range includes the target automatically. Effort **M**, risk on LibreOffice rendering of combo charts: phase D starts with a spike (tasks 7.1) and is deferred with recorded evidence if PowerPoint or the preview fails.

### D6. `table.total_row: bool`

Default `false`. `true` and ≥ 2 body rows: the table's `a:tblPr` gets `lastRow="1"`, so the **table style's own** total-row formatting applies (predefined styles: bold text and a top border or fill). Detected at render, not at analysis: the style is the frame's `a:tableStyleId`, else the `def` of `tableStyles.xml`. A predefined style (GUID in the predefined list) or a custom style holding an `a:lastRow` element → flag. Otherwise (no style, or a custom style without `a:lastRow`) → the last row's runs bold and `intent_shown_otherwise`.

`false` (or absent) now clears a template's `lastRow="1"`: the last data row of a plan without a total no longer looks like one (the fact above). Effort **S**.

### D7. `table.highlight_row` / `table.highlight_column`

Each optional: an integer is a 0-based index into `table.rows` (body rows) / `table.header`, the same indexes as the `table.rows[2]` edit paths; a string is matched against the rows' first cell / the header cells; a string of digits that matches no first cell is read as an index. Resolved against the plan, then mapped through the fit (a header moved into the body when the template table has none shifts the row by one). One row and one column at most; both may be set (their cross cell gets both).

Rendering: the cells' runs bold, and a cell fill of the table style's accent at a light tint (`schemeClr accentN`, `lumMod 20 % lumOff 80 %`), so the row reads as part of the same table. N is the accent the style is built on: read from a custom style's `firstRow` fill, or from a fixed GUID → accent map of PowerPoint's predefined styles (data only, in one module), else `accent1`. On a dark style (whole-table fill on `dk1`/`dk2`/`tx1`) the tint is skipped and bold alone renders the intent (`intent_shown_otherwise`). Not via `firstCol`/`lastCol`: they only reach the first and last column and look different from a middle highlight. Effort **M** (the style map).

### D8. `items[i].trend: up | down | flat`

Rendering, decided: a glyph `▲` / `▼` / `►` (U+25B2, U+25BC, U+25BA) as its own run before the figure in the item's `number` zone, copying the number run's properties at 60 % of its size, then a thin space. The figure keeps the template's colour, font and place; the glyph inherits them. These three code points are in the fonts PowerPoint and LibreOffice ship or fall back to.

Rejected: **semantic colours** — a theme has no "good/bad" colour (Context), and `down` is good news for a cost or a churn rate, so green/red would claim a meaning the field does not carry; **template icons** — no template we hold labels arrow icons, and supporting them needs per-item icon detection and a re-analysis: deferred (Q3).

The capacity check counts the glyph and space as one character of the figure's size. An item without a `number` zone, or a group that is not shown, gives `intent_not_shown`. Offered on every repeat group with a number zone (figures, and cards that show a number). Effort **S**.

### D9. Takeaway zone (phase C, amended 2026-10-15)

`SlidePlan.takeaway` is defined, required and checked by `ppt-builder-storytelling` (its D2): the conclusion the audience draws from the slide, always the first line of the speaker notes, not necessarily on the slide (owner, 2026-10-15). Phase C only lets a template that designed a takeaway zone show it.

- **Detection (analysis).** A text zone (body, caption, subtitle on a non-cover slide) is a takeaway zone (`Zone.takeaway = True`) when (1) its shape name — or for a placeholder, the layout placeholder's name — matches `lexicon.TAKEAWAY_NAMES` (`takeaway`, `key takeaway`, `key message`, `message cle`, `a retenir`, `so what`, `conclusion`), or (2) vision gave it a purpose containing those words; the labelling prompt's slot examples add "key message". Never by geometry alone (Q1). At most one per pattern (the first in reading order). `ANALYSIS_VERSION` 12 → 13; stored analyses refresh in the background (D20 of the base change). The built-in "Fred Chart" pattern gets its takeaway zone from the `takeaway` name; no deck edit needed.
- **Placement.** When the assigned template slide has a takeaway zone and the takeaway fits its room, the zone holds the takeaway and `bullets` do not fall into it. Otherwise the zone keeps today's behaviour (filled from `bullets`, else empty) and the takeaway is in the notes only: no body lead-line fallback, no misfit, no `needs_revision`, no summary note, since the takeaway is not meant to appear on the slide. The assignment does not score the takeaway: slide choice is unchanged.
- **Catalogue.** `takeaway zone ≤N words` on patterns holding the zone, so the model can keep a takeaway short enough when that template slide suits it. Effort **S**.

### D10. Edits, validation, summary

- `changes.py` `_FIELDS`: `chart` gains `highlight`, `sort`, `stacked_as` (text), `target` (`{value: number, label: text}`, also settable whole); `table` gains `highlight_row`, `highlight_column` (text or number), `total_row` (flag); `item` gains `trend`; the `takeaway` path comes from `ppt-builder-storytelling`. A kind edit clears intent fields with their parent (a cleared `chart` takes its `highlight`). `null` resets a field to its default.
- `unchanged` (identical-resend check, D26) compares intent fields too: changing only `highlight` rebuilds.
- Summary codes: `intent_not_shown`, `intent_shown_otherwise` with `field`; added to `BuildNoteCode`, `ppt_filler/types.ts`, `DeckSummaryButton.tsx` and fr/en locales ("Emphasis on Q3 could not be shown").

### D11. Phasing and order (by user value, then effort)

| Order | Field | Value | Effort | Phase |
|---|---|---|---|---|
| 1 | `chart.highlight` | high | M | A |
| 2 | `chart.sort` (+ bar top-down) | high | S | A |
| 3 | `chart.stacked_as` | medium | S | A |
| 4 | `table.total_row` | medium | S | B |
| 5 | `items[].trend` | medium | S | B |
| 6 | `table.highlight_row/column` | medium | M | B |
| 7 | takeaway zone | medium | S | C |
| 8 | `chart.target` | medium | M, risky | D (spike first) |

The takeaway zone comes third because it alone needs a re-analysis; A and B touch only rendering and plan coercion. Phases land in order on the same branch (`feat/ppt-builder-capability`), each tested by the owner before the next; there is no PR per phase: the owner opens a single PR for the whole capability. One change rather than four because the D1 rule, the note codes and the schema gating are shared.

## Risks / Trade-offs

- [More schema per call] → one-line descriptions, gated per template (D1); measured in the eval (tool-schema size before/after).
- [Weak models fill intents wrongly] → never blocks (D1), coerced spellings, notes name valid values; the eval checks first-call success does not drop.
- [LibreOffice preview: chart `a:alpha`, combo charts, `lastRow` of predefined styles] → each checked on rendered evidence (tasks); `.pptx` stays authoritative; a failing preview downgrades the decision (alpha → brightness by background luminance; target deferred).
- [Predefined table-style accent map is data to maintain] → fixed by the OOXML predefined list; unknown GUID → `accent1`.
- [Takeaway names miss a template's wording] → vision purpose as second signal; the author can rename the shape; the takeaway stays in the notes.

## Migration Plan

`ANALYSIS_VERSION` 13 in phase C only (automatic background re-analysis). No setting, no dependency. Migration note: impact none → patch; mention the cleared template `lastRow` (phase B). Existing bar charts keep their order.

## Owner decisions (2026-10-14)

The draft's recommendations were accepted on every open question:

- **Q1** No takeaway detection by geometry: shape or placeholder name and vision purpose only (D9).
- **Q2** ~~Takeaway fallback: the bold lead line of the body.~~ Superseded 2026-10-15: no on-slide fallback; the takeaway (field of `ppt-builder-storytelling`) is in the notes and fills a takeaway zone only (D9).
- **Q3** Trend: glyph only; template icons in a later change if a real template asks; never semantic colours.
- **Q4** `stacked_as` stays separate from `show`: `show` decides pie/doughnut labels, `stacked_as` the stack's geometry (re-checked at `25727177d`: `show: share` applies to pie and doughnut only and builds no 100 % stack).
- **Q5** Table highlight: bold + light tint of the table style's accent (needs the predefined GUID → accent map).
- **Q6** Target: combo chart on column, stacked column, line and area, after a spike; deferred with evidence if the preview fails.
- **Q7** One change, phases A–D on the same branch; the owner opens a single PR for the whole capability later (no PR per phase).
- **Q8** Category highlight on a multi-series chart: not rendered, noted (`intent_not_shown`).

## Open Questions

None.
