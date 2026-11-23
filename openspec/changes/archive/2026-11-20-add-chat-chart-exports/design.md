## Context

The typed chart part already contains up to 50 scalar rows. The frontend renders plots with Recharts as SVG and the source rows as a table. Saved conversations restore the same part.

## Goals / Non-Goals

**Goals:** Download the chart's stored data and plotted image from live or restored parts without new server work.

**Non-Goals:** Export rows beyond the chart part's limit or produce an image for the table-only view.

## Decisions

- Generate a minimal `.xlsx` workbook from `part.rows`, not the numeric values converted for Recharts. Retain the union of row keys in display order, preserve scalar cell types, and encode text as literal strings rather than formulas. Reuse the frontend's existing JSZip dependency.
- Rasterize the rendered SVG through an image and canvas for PNG. Resolve theme colors before serialization and leave the canvas transparent. This avoids an additional dependency and keeps the export tied to the visible plot.
- Put an icon-only download menu in the chart card, using the existing `IconButtonMenu`, `table_chart` and `image` icons, localized labels, and the existing toast pattern for failures. The table view exposes only Excel because it has no plotted graphic.

## Risks / Trade-offs

- [SVG serialization differs across browsers] -> Verify a real browser export and report failures in the UI.
- [Excel is bounded to the chart payload] -> Keep the source row limit explicit in the prompt.
