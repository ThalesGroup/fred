## Context

`ppt_builder` (change `ppt-builder-capability`, D1–D25) fills tables under D14: a table covering the slide's main area becomes a `table` zone when it is a data table (≥ 2 columns, no merges, body cells empty or sample text, one fill for every body cell); otherwise the slide is excluded `table`. The `table` field enters the tool schema only when the template offers a `table` kind. The built-in deck (D9) is "designed by the developer" and shipped as package data with its rules-only inventory; a test fails when the stored JSON differs from what the pipeline produces.

Facts (verified on `25727177d`, after the `ppt-builder-charts` deck edits):

- Inventory: `slide:266` (12th slide, part `ppt/slides/slide11.xml`, "Layout catalogue") is `included: false`, `exclusion_reason: "table"`, kind `section`, zones `[title]`. Its layout "Fred Table" (`slideLayout12.xml`) also stands alone as `layout:11`, kind `bullets`: its `table` placeholder (idx 101) has no `type`, so it is read as an `OBJECT` body, and since the charts change that body is `chart_capable`.
- `slide11.xml`: one free `graphicFrame` "Table 0" at (548640, 1508760), 11094415 × 4526280 EMU (≈ 873 × 356 pt, the layout's content area); `a:tblPr` empty; 3 columns (2926080 / 3566160 / 4602175 EMU); 7 rows of 502920 EMU; header cells `solidFill schemeClr accent1`, body cells no fill; every cell carries `lnL/lnR/lnT/lnB srgbClr DCDDE0` and `latin/ea/cs typeface="Arial"`; body text is the layout catalogue (real text).
- `table_spec` returns `None` twice over: non-sample body text, and (header not flagged) two distinct fills among "body" cells. Then `_apply_exclusions` excludes the slide.
- `ppt/tableStyles.xml` declares `def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"` (built-in "Medium Style 2 – Accent 1") and defines no style. Theme fonts are Arial (major and minor); default text size 18 pt.
- Notes (`notesSlide11.xml`): "Layout: Fred Table. Up to ~8 rows and 5 columns; split larger tables across slides."
- WP15 (base `verification.md`): Paintress's table (`firstRow="1" bandRow="1"`, Medium Style 2 – Accent 2, empty cells) renders correctly through the D14 path, banding included, in LibreOffice.

## Goals / Non-Goals

**Goals:** a `table` kind on the default configuration, sized for common comparisons (3–4 options × 6–8 criteria), styled by the theme; the existing D14 fit, shrink, column-dropping and two-part continuation rules unchanged.

**Non-Goals:** any analysis or rendering rule change; a second table variant; changing `_MAX_PARTS`; the "Fred Table" layout's own placeholder; a committed deck generator.

## Decisions

### D1. Fix the deck, not the rules

The analysis is right: a documentation table full of real text is a drawing to keep, not a table to fill, and the same rules protect customer decks (Paintress's Gantt grid stays excluded on the fill rule). Loosening `table_spec` (e.g. treating real body text as sample) would let customer reference tables be overwritten. The fix is the built-in deck, which the developer owns (D9).

Alternative rejected: a `kind: table` notes directive on the slide (`lexicon.KIND_NOTE`). It sets the kind but not a table zone, so the slide would be a `table` kind with nothing to fill.

### D2. The new table slide

Same slide (`slide:266`, so no stored deck plan pin breaks), same layout, same frame box. The table:

| | Value | Why |
|---|---|---|
| columns | 5: first 2926080 EMU (≈ 26 %), then 2042084 × 3 and 2042083, sum 11094415 | criterion + up to 4 options; the first column holds the longer label. Fewer columns are dropped from the right and the rest widened (D14) |
| rows | header 502920 EMU + 10 body rows of 402336 EMU (sum 4526280 = the frame) | the last row's height is the template's minimum row (`row_pt` 31.68 pt): 10 one-line rows at full size, more at the shrink floor |
| flags | `firstRow="1" bandRow="1"` | header detected; banding from the style |
| style | `a:tableStyleId {5C22544A-7EE6-4342-B048-85BDC9FD1C3A}` | the deck's declared default, accent1 = the deck's primary colour |
| cells | header: sample labels ("Criterion", "Option A"…), `b="1"`; body: empty; every cell `sz="1400"` on its run / `endParaRPr` | sample/empty passes `table_spec`; 14 pt fixes the measured size (else 18 pt default); no typeface: theme font. The header bold is explicit because the renderer copies the cell's run properties and LibreOffice does not apply the style's bold header |
| fills, borders | none on any cell | the style draws them, so a re-themed deck follows |

Measured room read back from the regenerated inventory: columns ≈ 33/22/22/22/22 chars per cell line, header + ≈ 10 lines of rows. Tests read these values from the inventory rather than hard-coding them.

Title: "Compare options side by side"; notes: "Layout: Fred Table. Header row and up to about 10 short rows, 5 columns; longer tables continue on a second slide."

### D3. How the binary is edited

A one-off script (lxml over the zip, run from the scratchpad, not committed): it rewrites only `ppt/slides/slide11.xml` and `ppt/notesSlides/notesSlide11.xml` and copies every other part byte for byte; then `make builtin-inventory`. The table relies on the style GUID like Paintress did; LibreOffice draws it (preview in `verification.md`).

Alternative rejected: a committed deck generator script (more code to keep for a one-slide edit; the deck is a designed asset, D9).

### D4. No analysis version bump

The rules are unchanged, so `ANALYSIS_VERSION` stays; only the built-in inventory changes (its `template_sha256` and the `slide:266` pattern). `test_stored_inventory_is_what_the_pipeline_produces_for_the_shipped_deck` enforces it.

### D5. What the model sees

Once the pattern is a `table`, the existing code adds the `table` field to the schema and the catalogue line (`table 2 to 5 columns (≈33/22/22/22/22 chars per cell line), header + ≈10 lines of rows`) and the guide sentence ("a comparison across criteria → table"). Nothing to write; the tests assert it.

### D6. Owner decisions (2026-10-14)

- **Three-part tables:** keep the 2-part cap (`_MAX_PARTS`) for tables for now. A table needing three slides gets `needs_revision`; the model restructures it.
- **The "Fred Table" layout:** kept as is. `layout:11` stays a `bullets` variant (chart-capable body) whose body is the layout's untyped `table` placeholder; the example slide's table stays a free frame.
- **Size:** no denser variant for now; 5 columns × 10 short rows is the only built-in table.

## Risks / Trade-offs

- [LibreOffice preview may not draw the built-in style the same as PowerPoint] → checked on the template slide and a built deck (`verification.md`); PowerPoint rendering checked by hand only.
- [The "Layout catalogue" content disappears from the example deck] → it only documented layouts; each slide's notes already describe its layout.

## Migration Plan

None for stored data: customer analyses are untouched, the built-in inventory ships with the package. Agents on the built-in deck get the `table` field at their next turn after deployment.

## Follow-ups

- **Possible double zone on a table inside a placeholder (not fixed here, not reproduced).** Reading the code, a table frame bound to an untyped/`obj` placeholder (PowerPoint's "insert table" icon in a content placeholder) could get both a `body` zone (`_slot_role` does not check the record kind) and a `table` zone. It does not affect this change (the built-in table is a free frame); it needs a customer-style fixture to confirm before any fix.
