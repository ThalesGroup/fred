## Why

`ppt_builder` (GitHub issue #2679) fills tables only into a data table the template holds (base change `ppt-builder-capability`, D14). The built-in Fred template, used by every agent without its own template, had no such table: its table slide (`slide:266`, 12th in deck order, part `ppt/slides/slide11.xml`, "Layout catalogue") was analysed as excluded (`exclusion_reason="table"`). The tool schema then carried no `table` field on the built-in deck, and a `table` the model sent anyway was refused with `table: this template has no table slide`. In the WP15 eval the built-in deck recast tabular prompts into runs of repeated slides (0/0 tables used).

Root cause, confirmed on `25727177d`: the slide held a documentation table, not a fillable one. `analysis.table_spec` rejects it on two rules:

- its body cells hold real text (`Fred Title`, `Opening slide`, `title, subtitle, meta`…), not empty or sample text;
- its `a:tblPr` is empty (no `firstRow="1"`), so the header row counts as body, and the header cells' `accent1` fill differs from the unfilled body cells (rule "one fill for every body cell").

With no table zone, `_apply_exclusions` sees a table covering ≥ 15 % of the slide and excludes the slide. The table also hard-coded `srgbClr DCDDE0` borders and an `Arial` typeface per cell, and referenced no table style: even accepted, it would not have followed the theme.

## What Changes

- **Built-in deck only.** The "Fred Table" example slide of `fred_template.pptx` (same slide id `slide:266`, same "Fred Table" layout, same frame position and size) becomes a real data table: header row + 10 empty body rows, 5 columns (first column wider, for the criterion), `firstRow="1" bandRow="1"`, the table style the deck already declares as default ("Medium Style 2 – Accent 1", `{5C22544A-…}`), no per-cell fill, border or typeface, cell size 14 pt. Title and notes rewritten to show a comparison.
- `fred_template.inventory.json` regenerated with `make builtin-inventory`: `slide:266` becomes an included pattern of kind `table`.
- No analysis, assignment, render or schema code change: the existing D14 rules (detection, fit, column dropping, row growth, shrink, continuation over two slides) apply as they are. `ANALYSIS_VERSION` unchanged; customer templates are not re-analysed.
- Tests pin the built-in table slide and an end-to-end build of a common comparison (4 offers × 6 criteria) on the default configuration.

## Capabilities

### New Capabilities

- none

### Modified Capabilities

- `ppt-builder`: adds requirement "The built-in template offers a data table slide". The base requirements live in the in-flight change `ppt-builder-capability`; this change is applied and archived after it.

## Impact

- `libs/capabilities/fred-capability-ppt-filler/fred_capability_ppt_filler/builder/assets/fred_template.pptx` (one slide and its notes edited) and `fred_template.inventory.json` (regenerated).
- Tests: `tests/test_builtin_template.py`, `tests/test_table_slides.py`.
- No frontend change (`table` kind already known), no dependency, no migration, no API change. The Help Center does not say the built-in template lacks a table: no edit.
- Sequencing: the sibling change `ppt-builder-charts` edited this deck first (it added "Fred Chart Wide" and made the "Fred Table" layout's placeholder chart-capable); this change was built on top of it.
- Migration: same PR as `ppt-builder-capability`, whose migration note already covers the built-in template; no operator action.
- Tracking: #2679.
