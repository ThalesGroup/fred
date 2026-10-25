## Verification (2026-10-16)

All commands run in `libs/capabilities/fred-capability-ppt-filler` unless stated.

### Tests

- `make test`: **816 passed, 5 skipped** (the skips need a reference template that is not in the repo). Before this change: 772 passed. The 44 new test cases:
  - `tests/test_chart_slides.py`: point coercion (8 written forms: point lists, objects, `data` entries, parallel lists in a series and at chart level, chart-level `points`, numeric categories), per-axis units and bubble sizes, a list of sizes as data while `size: "large"` and an `x_axis` object stay design keys, `x` read as categories on a column chart, the new type names (`stacked bar` → `stacked_bar`), a points chart surviving its dump with its unread values; one case per D3 message (14); a long axis title measured with its unit; each new type drawn natively with `schemeClr` accents, no `srgbClr` and the theme body font (5, including `BAR_STACKED_100`); scatter axis titles, number formats, point names up to 12 points and none above; bubble size line and bubble scale; intents (point highlight, `sort` told on bubble and radar, a stacked bar sorted by totals); axis fields told on a column chart; example charts of the new types reused in phase B (scatter, radar, a 100 % stacked bar refilled as a value stack); a point edit and a `chart.type` edit from scatter to column refused with the shape message; the tool description, catalogue and schema enum.
  - `tests/test_story_checks.py`: radar and stacked bar take the spread question; a scatter does not; a scatter axis mixing units is refused while units differing between axes pass; points are sourced figures (no `source` refused, a found x value passes, nothing found refused once).
  - `tests/test_chart_intents.py`: two expected messages updated for `stacked_bar`.
  - `tests/test_chart_slides.py`: the unknown-type fallback test now uses `waterfall` (radar is a type now).

### Quality gates

- `make code-quality` (ruff check, `ruff check --select I`, `ruff format --check`, bandit, detect-secrets, basedpyright with the module baseline): all green. Ruff: "All checks passed!" twice, "68 files already formatted"; bandit: "No issues identified"; basedpyright: 0 errors, 1 warning (`tests/builder_decks.py` `__all__`, present before this change).
- `openspec validate ppt-builder-more-chart-types --strict` (repo root): valid.
- Help Center (fr + en, `guides/prepare-powerpoint-template.md`, `features/capabilities.md`): `npx prettier --check` on the four files, clean. No frontend `make` target was run.
- The generated frontend clients do not carry the chart type enum (`grep stacked_column` over `apps/` finds no TypeScript): no regeneration.

### Built-in template

`ANALYSIS_VERSION` 14 → 15; `make builtin-inventory` rewrote `builder/assets/fred_template.inventory.json` (only `analysis_version` changes).

### Rendered evidence

The four types of the spec scenarios (stacked bar, radar, scatter with "Price (€)" / "Units sold" and one point name, bubble with "Bubble size: Revenue (M€)") were built on the built-in template and converted with LibreOffice (`soffice --headless --convert-to pdf`); checked by eye: horizontal stacked bars in accent 1 and 2 with a legend below, a radar with markers and two outlines, a scatter with markers only and titled axes, translucent bubbles sized by revenue. The PDFs are not committed; the `.pptx` stays authoritative.

### Not proven yet

- Task 5.1: the evaluation prompts, edits and metrics (expected chart type chosen, first call, scatter/bubble axes titled) are written in `eval/prompts.py` and `eval/run_eval.py`; the `make eval` run against a live model has not been run.
- Point highlights on a scatter are drawn as per-point markers, which LibreOffice ignores; PowerPoint shows them.

## Live run (5.1, 2026-10-25)

- Through the revision harness (`~/fred-tmp/revision-evals/charts-r1..r3`), not `make eval`: scatter, bubble, radar and stacked bar chosen as asked. Bubble pass in r1-r3; stacked + bubble pass in r3; radar capped at 3 series (partial); scatter labels overlap (partial). r3 6/3/0 on 9 requests, r2 6/6/1 on 13.
