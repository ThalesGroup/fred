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
