## Context

`chart.render` stores a flat, bounded row set and chart type in a typed UI part. The frontend uses Recharts 2.15.4 and already shares a ten-color KPI palette. See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:** Keep one flat-row contract and both the live and restored paths. Make view choice semantic and distinguish groups within a bar chart.

**Non-Goals:** Generate graph or nested data for Sankey and sunburst; infer histogram bins from raw observations; change chart auto-selection threshold or download formats.

## Decisions

- Add chart type variants to the existing enum and renderer. Reuse `x_key` and `y_keys`; no second chart payload or persisted migration. Recharts primitives compose horizontal and stacked variants.
- Restrict scatter to a numeric x and one numeric y, single-measure share and shape views to one nonnegative y, and composed to at least two y series (first bar, remainder lines). Keep row order and values unchanged. Alternative: coerce or sort inputs, which would misrepresent SQL results.
- Add optional `group_key` for long-form bars with one y value per row. Validate unique category/group pairs and at most eight groups. Pivot rows only for Recharts; retain the original rows for the table and Excel export. Assign a distinct palette color to each group within that chart. For saved chart parts without `group_key`, infer the sole extra column only when categories repeat and category/group pairs are unique.
- Keep all work bounded by the existing 50-row and 50,000-character limits; rendering remains client-side and stateless across pods.

## Risks / Trade-offs

- Dense views can become hard to read with 50 rows -> retain the source table and tell the agent to use concise result sets.
- Some views have stronger semantics than their raw data shape -> tool guidance specifies when to use them; validation rejects incompatible mappings.

## Migration Plan

Existing chart parts use unchanged type names and payload fields. Deploy backend and frontend together; rollback leaves already-saved new chart types with the existing unavailable fallback.
