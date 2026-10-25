# Verification — ppt-builder-builtin-table-slide

2026-10-14, branch `feat/ppt-builder-capability`, on top of `25727177d`.

## Root cause

Confirmed on `25727177d`: `table_spec` returned `None` for the "Fred Table" example slide (body cells held real layout text; `a:tblPr` empty, so the `accent1`-filled header counted as a body row with a second fill), and `_apply_exclusions` excluded `slide:266` as `table`.

## Deck edit (D3)

One-off lxml script over the zip (scratchpad, not committed): only `ppt/slides/slide11.xml` and `ppt/notesSlides/notesSlide11.xml` rewritten, every other part copied byte for byte; then `make builtin-inventory`.

| | Before | After |
|---|---|---|
| title | "Layout catalogue" | "Compare options side by side" |
| frame | (548640, 1508760), 11094415 × 4526280 EMU | unchanged |
| `a:tblPr` | empty | `firstRow="1" bandRow="1"`, `tableStyleId {5C22544A-7EE6-4342-B048-85BDC9FD1C3A}` |
| grid | 3 columns (2926080 / 3566160 / 4602175) | 5 columns (2926080 / 2042084 × 3 / 2042083) |
| rows | 7 × 502920 | header 502920 + 10 × 402336 |
| cells | `accent1` header fill, `srgbClr DCDDE0` borders, `Arial` typefaces, layout text | no fill, border or typeface; `sz="1400"`; header "Criterion", "Option A"…"Option D" (`b="1"`), body empty |
| notes | "Up to ~8 rows and 5 columns; split larger tables across slides." | "Header row and up to about 10 short rows, 5 columns; longer tables continue on a second slide." |

Inventory diff: `template_sha256` and the `slide:266` pattern only (label, kind `section` → `table`, `included` false → true, `exclusion_reason` `table` → null, new zone `sp:12` role `table`: header, columns ≈ 33/22/22/22/22 chars, `row_pt` 31.68, `max_lines` 10, 14 pt). No other pattern changed; `ANALYSIS_VERSION` unchanged.

## Automated checks

| Check | Where | Result |
|---|---|---|
| `make test` | `libs/capabilities/fred-capability-ppt-filler` | 671 passed, 5 skipped (reference corporate templates not provided) |
| `tests/test_table_slides.py`, `tests/test_builtin_template.py` | same | 24 passed (4 new tests) |
| `ruff check --select I .` | same | clean |
| `ruff check`, `ruff format --check`, `basedpyright --baseline-file .baseline/basedpyright-baseline.json` on this change's files | same | clean, 0 errors |
| `openspec validate ppt-builder-builtin-table-slide --strict` | repo root | valid |

Package-wide `ruff check`, `ruff format --check` and basedpyright reported findings only in files another in-flight change was editing at the same time (`render.py`, `charts.py`, `plan.py`, `tests/test_chart_intents.py`, uncommitted); none in this change's files.

## What the tests prove

- `slide:266` is an included `table` pattern with a header row and 5 columns, the first the widest; nothing on the built-in deck is excluded for `table`; the schema has a `table` field and the description quotes the room read from the inventory.
- 4 offers × 6 criteria build on `slide:266` with no problem and no note; the delivered table holds exactly the header and rows sent, keeps the style GUID, and has no `srgbClr`, no typeface and no template text ("Option A").
- 16 rows continue on a second table slide, header repeated on both, all 16 rows delivered.
- 6 columns → `needs_revision` "6 columns given, max 5".

## Preview (LibreOffice)

- Built deck (cover, 4 × 6 comparison, 16-row plan split 8 + 8) built through `assign` / `assignment.deck` / `render_deck` with no LLM, converted with `TMPDIR=$HOME/fred-tmp soffice --headless --convert-to pdf`: accent1 header with white bold text, banded body rows, white cell borders from the style, theme font, no overflow. File kept outside the repo (`scratchpad/charts-evidence/table.pdf`).
- The template's own slide 12 renders as an accent1 header over 10 banded empty rows.

## Not proven

- PowerPoint rendering of the style GUID without a style definition in `tableStyles.xml` (expected: PowerPoint resolves built-in style GUIDs; not opened in PowerPoint here).
- The model actually choosing tables on the built-in deck (the WP15 eval was not re-run).
