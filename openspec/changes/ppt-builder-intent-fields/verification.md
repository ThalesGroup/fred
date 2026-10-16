# Verification — ppt-builder-intent-fields

## Phase A — chart emphasis (2026-10-14, branch `feat/ppt-builder-capability`)

### Automated checks

| Check | Where | Result |
|---|---|---|
| `make test` | `libs/capabilities/fred-capability-ppt-filler` | 672 passed, 5 skipped (reference corporate templates not provided) |
| new `tests/test_chart_intents.py` | same | 33 tests, all passing |
| `ruff check .`, `ruff check --select I .`, `ruff format --check .` | same | clean (61 files) |
| `basedpyright --baseline-file .baseline/basedpyright-baseline.json` | same | 0 errors; 1 warning already present (`__all__` in `tests/builder_decks.py`) |
| `npx tsc --noEmit -p .` | `apps/frontend` | 0 errors |
| `npx vitest run src/rework/features/capabilities/ppt_builder src/rework/features/capabilities/ppt_filler/DeckSummaryButton.test.tsx` | same | 7 files, 46 tests passed |
| `prettier --check`, `eslint` on the touched files | same | clean |
| `openspec validate ppt-builder-intent-fields --strict` | repo root | valid |

### What the tests prove

- Plan: `descending`, `Décroissant`, `largest first`, `true` → `desc`; `croissant` → `asc`; `as given` → `given`; `100%`, `pourcentage` → `percent`; aliases `order`, `sort_by`, `stacking`, `emphasis`; a one-entry list is one name. Unread words (`sort: sideways`, two highlight names) are kept in `asked_intents` across a re-validation; the schema offers the enums and says "never a colour".
- Rendering: a chart without intents has no `c:dPt`, no `a:alpha`, bar order unchanged; `desc`/`asc` reorder categories with their values while the plan keeps the order written; ties are stable; a clustered chart sorts by its first series, a stacked one by totals; a sorted bar puts the largest on top; a highlighted category gives its `c:dPt` `accent1` and every other point `tx1` + `a:alpha 35000`, no `srgbClr`, its data label bold while the others still show; a highlighted slice takes `accent1` and no other accent appears; a highlighted series is `accent1` at 3 pt, the others `tx1` at 1.5 pt with no markers, alternating 35 % / 55 %; `stacked_as: percent` builds `COLUMN_STACKED_100` with a `0%` axis.
- Notes (D1): unmatched name, a colour word, a category on a two-series chart, several names, a category on a one-series line or area chart, sort on line/area, percent on a line, unread sort/stacking words — each builds the deck, sends the agent line with its remedy and records `intent_not_shown` with its field; one note text on slides 2 and 4 is one `Slides 2, 4:` line.
- Changes: `chart.highlight`, `chart.sort` (`décroissant`), `chart.stacked_as` edits keep the template slide, `unchanged` sees them, and the highlight renders.
- Frontend: per-field wording for `highlight` and `sort`, generic wording for an unknown field; fr/en hold every code.

### Preview evidence

`intent-phase-a.pdf` (scratchpad `charts-evidence/`, built from `builtin_template()` → `assign` → `render_deck`, no LLM, converted with LibreOffice): unchanged column; column highlight Q3; pie highlight South; doughnut highlight East (bold `bg1` label on the accent, `tx1` labels on the grey ring); bar sorted desc with the largest on top; column sorted desc + highlight; three-series line with 2025 highlighted; 100 % stacked column; the two noted line charts drawn without the intent.

Found and fixed during the preview: LibreOffice lays a series-level `a:alpha` over every point, which washed out the highlighted bar, so each point now takes its own colour; it also ignores a point's own marker colour on a line, so a category highlight on a one-series line is noted instead of drawn.

### Not proven

- PowerPoint rendering (checked by hand only by the owner).
- A dark-background theme (no such template in the test assets): the muted colour is `tx1` with opacity, so it should stay below the accent there too.
- On a highlighted pie with more than three slices, the legend tells the muted slices apart only by two tones (accepted limit, design D3).

## Phases B and C — tables, key figures, slide takeaway (2026-10-16, branch `feat/ppt-builder-capability`)

Phase D (chart target) was dropped by the owner the same day (design D5): nothing to verify.

### Automated checks

| Check | Where | Result |
|---|---|---|
| `make test` | `libs/capabilities/fred-capability-ppt-filler` | 884 passed, 5 skipped (reference corporate templates not provided); re-run after Q9/Q10 (2026-10-16) |
| new `tests/test_table_intents.py` | same | 21 tests, all passing (3 for Q9) |
| new `tests/test_figure_trend.py` | same | 15 tests, all passing |
| new `tests/test_takeaway.py` | same | 14 tests, all passing (1 new and 2 extended for Q10) |
| `make code-quality` (ruff check, `--select I`, format check, bandit, detect-secrets, basedpyright with its baseline) | same | clean; basedpyright 0 errors, the 1 warning already present (`__all__` in `tests/builder_decks.py`) |
| `make builtin-inventory` | same | regenerated: `analysis_version` 17, the "Fred Chart" slide's `takeaway` placeholder flagged |
| `npx prettier --check` on the touched frontend files | `apps/frontend` | clean |
| `npx tsc --noEmit -p .` | `apps/frontend` | clean |
| `npx vitest run src/rework/features/capabilities/ppt_filler/DeckSummaryButton.test.tsx` | `apps/frontend` | 8 passed |
| `openspec validate ppt-builder-intent-fields --strict` | repo root | valid |

Not run here: the frontend `eslint` (frontend `make` targets off limits while the stack runs).

### What the tests prove

- Tables: `total`, `dernière`, `yes` read as a total; a highlight given as text, index or list keeps its first entry, across a re-validation. No intent leaves the table as before (no `lastRow`, no fill). `total_row` sets `lastRow="1"` on the predefined Medium Style 2 and on a custom style holding `a:lastRow`; a template table flagged `lastRow` is cleared when the plan has no total; a custom style without `a:lastRow` gets the last row in bold with `intent_shown_otherwise`; a one-row total is `intent_not_shown`. A row named by its first cell (case and accents ignored) is bold and tinted `accentN` at `lumMod 60000 / lumOff 40000` (Q9: the strong tint on Medium Style 2 and Light Style 1 – Accent 1; a navy `accent1` takes `lumMod 40000 / lumOff 60000`), header and other rows untouched, no `srgbClr`; Medium Style 2 – Accent 2 tints `accent2`, a custom style its header row's accent (`accent3`); a column named by its header tints its body cells only; unmatched row and column references are noted with the valid first cells or headers; a plan without header on a template with one shifts the row (rows[0] is the header: noted); a dark style shows bold only with `intent_shown_otherwise`. The 74 predefined GUIDs are listed once. A table split over two slides keeps its total on the last part and its highlighted row on the part holding it. The three edit paths apply; the tool schema and description offer them.
- Key figures: `hausse`, `↑`, `en baisse`, `stable`… read; an unread word is kept for the note across a re-validation. On the built-in "Fred Key Figures" slide each figure reads `▲ 42 %`, `▼ 12`, `► 3,5 M€`, the arrow its own run at 60 % of the figure's size, with no colour written; figures without trend are unchanged; a trend on cards without figures, on an item without a number, or with an unread word is noted (`intent_not_shown`, `trend`). `items[1].trend` edits apply; `trend` is in the schema and description only where items show a figure.
- Takeaway zone: the built-in template has one, the "Fred Chart" `takeaway` card, quoted `takeaway zone ≤27 words` in the catalogue; a zone named "Key message" is flagged before a later "À retenir" one; no flag from geometry, on a quote slide or on a title; a layout placeholder named "Key takeaway" is found through the slide; a vision purpose "key message" flags the zone.
- Takeaway shown: by default the card holds the bullet and the takeaway is in the notes only; with `show_takeaways` and a user message "affiche les messages clés sur les slides" the chart slide with the card is chosen and the card holds the takeaway (notes keep it too); the flag without such a message builds as before and the agent is told; with the flag honoured a bullet no longer falls into the card (`needs_revision` names the bullets); a takeaway longer than the card stays in the notes, the bullet fills the card and the agent is told to shorten it; a bullets slide without zone is built as before with `intent_not_shown` / `takeaway` and an agent note (Q10); two chart slides on request both take the slide with the card (before Q10 the second went to the wide chart slide: the test fails on the previous `assign.py`), and without the request both stay on the wide chart slide as before; a `changes` edit of the takeaway keeps the flag and refills the card; `show_takeaways` is in the schema and description only when the template has a takeaway zone.

### Preview evidence

Scratchpad `evidence/intent-phases-b-c.pdf` and `takeaway-shown.pdf`, built from `builtin_template()` → `assign` → `render_deck` (no LLM), converted with LibreOffice: a table without intents; the same with `total_row` (LibreOffice draws the style's total row, an accent-filled last row); `highlight_row: "Offre B"` and `highlight_column: "Prix (k€)"` (bold); three key figures with their arrows, smaller, in the figure's colour; the chart slide with its card holding the takeaway; the default slide, its card holding the bullet.

Found during the preview: on the built-in style (Medium Style 2) the light tint equals the table's unbanded row colour and is lighter than its banded rows, so the highlight reads mostly through bold (Q9). After Q9 (2026-10-16), LibreOffice previews of a highlighted row and column on Medium Style 2 (built-in), Medium Style 2 – Accent 2 and Light Style 1 – Accent 1: the highlight stands out from both bands, its bold dark text readable (computed contrast 6.2:1 on the built-in accent 1, 8.6:1 on accent 2).

### Not proven

- PowerPoint rendering (checked by hand only by the owner), in particular the total row of the other predefined styles.
- The vision path end to end: the purpose rule is unit-tested; no template with an unnamed key-message zone was labelled.
- The evaluation prompts were not run (real LLM).
