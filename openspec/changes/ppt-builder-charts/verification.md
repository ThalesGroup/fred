# Verification — ppt-builder-charts

## Phase A (2026-10-14, branch `feat/ppt-builder-capability`)

### Automated checks

| Check | Where | Result |
|---|---|---|
| `make test` | `libs/capabilities/fred-capability-ppt-filler` | 604 passed, 5 skipped (reference corporate templates not provided) |
| new `tests/test_chart_slides.py` | same | 41 tests, all passing |
| `ruff check .`, `ruff check --select I .`, `ruff format --check .` | same | clean (60 files) |
| `basedpyright --baseline-file .baseline/basedpyright-baseline.json` | same | 0 errors; 1 warning already present (`__all__` in `tests/builder_decks.py`) |
| `npx tsc --noEmit -p .` | `apps/frontend` | 0 errors |
| `npx vitest run src/rework/features/capabilities/ppt_builder src/rework/features/capabilities/ppt_filler/DeckSummaryButton.test.tsx` | same | 7 files, 45 tests passed |
| `npx vitest run src/rework/features/helpCenter` | same | 18 tests passed |
| `prettier --check`, `eslint` on the touched files | same | clean |
| `openspec validate ppt-builder-charts --strict`, `openspec validate ppt-builder-capability --strict` | repo root | valid |
| `scripts/migration_guides.py check-pr --base origin/swift --worktree` | repo root | valid (the existing `ppt-builder-capability` note was extended) |

The ppt_builder client was regenerated with the two steps of `make update-ppt-builder-capability-api` run by hand (`apps/fred-agents/.venv/bin/python -m fred_runtime dump-openapi ppt_builder`, then `npx --no-install @rtk-query/codegen-openapi …/pptBuilderCapabilityOpenApiConfig.json`), to avoid the target's `npm ci` under the owner's running Vite.

### What the tests prove

- Analysis: the built-in "Fred Chart" example slide and the new "Fred Chart Wide" slide are included `chart` patterns (chart zone `ph:101`, `chart_type` `column`, 12 categories quoted); an example slide's one free main chart is its zone; two charts keep a slide out (`chart`), a small chart keeps it uncopyable; only a large `OBJECT` placeholder is chart-capable (on the built-in deck, only the "Fred Table" layout's); vision cannot turn a chart slide into another kind or another slide into `chart`.
- Plan: aliases, `{category: value}` pairs, written numbers (`"45 %"`, `"1 200"`, `"55,5 %"`, `"€3.5"`), unit inference only when every value agrees, an unknown type built as `column` and remembered across a re-validation, design keys set aside (not a revision), unknown keys reported as lost text.
- Validation (D5): each message — length mismatch, non-number, pie with two series, six series, eight slices, no data, twenty categories against a room of 12, an over-long label — with its remedy.
- Placement (D3): a chart with a takeaway goes to "Charts stay native and editable", a bare chart to "One chart across the slide"; on PowerPoint's default template the chart lands in the "Title and Content" area at its box, reported as `other_kind: chart` and in the agent note, the empty placeholder gone; bullets taking the only content area leave a "no place" problem; a template with no place at all gets "this template has no slide for a chart" with the table / figures / bullets options read from the template; a chart slide is never chosen for a slide without a chart; chart repeats are never asked to become another kind.
- Drawing (D4): the seven types build the matching `XL_CHART_TYPE` with the plan's categories and values; three series reference `accent1..3` and the chart XML holds no `srgbClr`; `+mn-lt` is the chart font; the frame sits on the zone's box and no example frame is left; title and legend rules (adapted from #3058); `#,##0.0" M€"` on the axis and data labels; pie labels in percent; a `radar` request is drawn as columns with the agent note and the `chart_type_changed` summary note.
- Changes (D8): `chart.series[0].values[2]` edits the value on the same template slide; a category appended without its values is named; a kind edit to `bullets` clears `chart` (`cleared == {2: ["chart"]}`); `chart: null` clears it.
- Tool (D9): the schema offers `chart` only when the template can host one; the description and catalogue quote the room; a template without a chart slide reads "or a chart in place of the bullets".

### Rendered evidence (LibreOffice, built-in template, no LLM)

Built through `assign` and `render_deck` (script kept in the session scratchpad, not committed), converted with `soffice --headless --convert-to pdf`, every page looked at:

- `column.pdf`: revenue by quarter on "Charts stay native and editable" (accent 1, values `12,4 M€`… above the bars, takeaway beside it); two years by region on the wide slide (accent 1 and 2, legend under the plot).
- `pie.pdf`: a four-slice pie with its takeaway (percentages outside, legend under); a five-slice doughnut on the wide slide (white percentages on the ring).
- `stacked_area.pdf`: three stacked series by year on the wide slide; twelve months of an area chart (`k` unit on the axis) with its takeaway.

Nothing overflowed; labels read at 12 pt; every colour is a theme accent. The review thumbnails of both chart slides now show their chart.

### Not proven

- PowerPoint rendering: checked through LibreOffice only; the `.pptx` files open in python-pptx with `has_chart`.
- The eval prompts `sales_charts` and `market_shares` and the chart metrics were added but not run: the harness needs a live LLM.
- Room constants (3 em per category, 2.2 lines per bar, caps 12/24) were tuned on the built-in deck only.

## Pie labels mode `show` (2026-10-14, design D12)

| Check | Where | Result |
|---|---|---|
| `make test` | `libs/capabilities/fred-capability-ppt-filler` | 625 passed, 5 skipped (21 new in `test_chart_slides.py`) |
| `ruff check .`, `ruff check --select I .`, `ruff format --check .` | same | clean (60 files) |
| `basedpyright --baseline-file .baseline/basedpyright-baseline.json` | same | 0 errors; the 1 known warning |
| `npx tsc --noEmit -p .` | `apps/frontend` | 0 errors |
| `npx vitest run src/rework/features/capabilities/ppt_builder src/rework/features/capabilities/ppt_filler/DeckSummaryButton.test.tsx` | same | 7 files, 45 tests passed |
| `prettier --check`, `eslint` on the touched files | same | clean |
| `openspec validate ppt-builder-charts --strict` | repo root | valid |

What the tests prove: `show`, `display`, `labels_as`, `show_as` with loose words (`numbers`, `absolute`, `pourcentages`, `%`, `les deux`) give the mode and survive a re-validation; unset stays `share`; `labels` still names the categories; `bubbles` is a revision on a pie. The chart XML per mode: unset/`share` → `showVal 0`, `showPercent 1`, `0%`; `value` → `1`, `0`, `#,##0" collaborateurs"`; `both` → `1`, `1`, the same format linked, separator a line break. `unit: "collaborateurs"` in `share` → the agent note and the `chart_shows_shares` summary code; `unit: "%"` or `show: value` → none; `show` on a column chart → the "not applied" note only. `{"op": "edit", "field": "chart.show", "value": "value"}` re-renders the pie with values and no note.

Rendered evidence (built-in template, `assign` + `render_deck`, no LLM, LibreOffice): `pie-show.pdf` in the session scratchpad (not committed), one pie (27 / 15 / 58, unit `collaborateurs`) per mode, every page looked at — `share`: `27%` `15%` `58%`; `value`: `27 collaborateurs`…; `both`: `27 collaborateurs` over `27 %`. All labels outside the slices, readable, no overlap.

Not proven: PowerPoint's rendering of the linked `both` labels.

## Phase B

Not started: waits for the owner's test of phase A (tasks 7–8).
