## Context

See proposal.md - Why. `geo.render_points` already returns a `GeoPart` with a GeoJSON FeatureCollection. The shared local built-in contract handles validation errors as tool results without UI parts. The Leaflet renderer already accepts GeoJSON shapes and draws point markers above map overlays. Corpus coordinates reach the agent through existing `knowledge.search` snippets.

## Goals / Non-Goals

**Goals:** Preserve point-only calls, bound the number of vertices to the existing 100-point limit, and let the agent correct invalid zone calls through the existing tool error path.

**Non-Goals:** Exhaustive extraction of GPS coordinates from the corpus, geocoding, automatic point ordering, multipolygons, or a separate zone tool.

## Decisions

- Add an optional boolean to the existing arguments, defaulting to false. This keeps existing callers and the generic ReAct, Deep, Graph, and `ToolContext.invoke_tool` routes unchanged. A separate tool would duplicate discovery and map rendering.
- Validate at least three distinct coordinate pairs when zone mode is true. Reject incomplete boundaries instead of silently drawing a line or inventing a third vertex.
- Emit a GeoJSON Polygon feature after the Point features, with the first coordinate repeated at the end. Use a light fill and the existing map renderer, which already supports GeoJSON polygons. Keeping the markers as separate features preserves labels, hover details, and the location list.
- Describe zone mode in the built-in tool's available-tools description, not in the platform prompt. Agents use retrieved corpus coordinates; the tool itself never reads documents.

## Risks / Trade-offs

- [An agent may order selected points incorrectly] - Guidance asks for boundary order; the tool preserves that order rather than guessing geometry.
- [A self-intersecting polygon may be visually confusing] - The tool does not infer or repair topology; users can correct the selected point order.
- [Multiple chat maps may add rendering work] - The existing 100-point argument limit bounds zone vertices, and no new network request or shared state is added.

## Migration Plan

No data migration. The optional argument defaults to the existing behavior. Rollback removes the argument and polygon emission; existing point-only calls remain valid.
