## 1. Built-in deck

- [x] 1.1 Edit the "Fred Table" example slide (`ppt/slides/slide11.xml`) of `builder/assets/fred_template.pptx` per design D2: same slide id, layout and frame box; 5 columns, header + 10 body rows, `firstRow="1" bandRow="1"`, `tableStyleId {5C22544A-7EE6-4342-B048-85BDC9FD1C3A}`, header sample labels, empty body cells, `sz="1400"` per cell, no cell fill/border/typeface; comparison title; notes rewritten (D2)
- [x] 1.2 Record the edit method and the before/after XML facts in `verification.md` (D3)
- [x] 1.3 `make builtin-inventory`: `slide:266` included, kind `table`, a `table` zone with `header: true` and 5 columns; no other pattern changes (diff reviewed)
- Verification: `test_builtin_template.py` passes on the regenerated JSON; the patterns diff lists only `slide:266`

## 2. Tests and preview

- [x] 2.1 `test_builtin_template.py`: `slide:266` is `table`, included, header row, 5 columns, room read from the inventory (no hard-coded chars); `table` field present in `_args_schema(builtin)` and the table line in `_description`
- [x] 2.2 `test_table_slides.py` on the built-in template: 4 offers × 6 criteria builds on `slide:266` with no `needs_revision` and no note; the delivered table keeps `tableStyleId`, has no `srgbClr`, no typeface and no template cell text; 16 rows continue on a second table slide with the header repeated; 6 columns → `needs_revision` naming "max 5"
- [x] 2.3 Preview: render the built-in template's table slide and one built deck through LibreOffice; check header colour, banding and fonts follow the theme (reference in `verification.md`)
- Verification: package `make test` green

## 3. Docs and close-out

- [x] 3.1 Help Center (`apps/frontend/src/rework/features/helpCenter/content/{fr,en}/`): edit only if it says the built-in template has no table
- [x] 3.2 Migration: covered by the PR's `ppt-builder-capability` note (no operator action)
- [x] 3.3 Package `make test`; `ruff check`, `ruff check --select I`, `ruff format --check`; basedpyright with baseline; `openspec validate ppt-builder-builtin-table-slide --strict`
- Verification: `verification.md` with test counts, inventory diff, preview evidence and what stays unproven (PowerPoint rendering checked by hand only)
