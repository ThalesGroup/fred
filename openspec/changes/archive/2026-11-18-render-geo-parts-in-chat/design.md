## Context

See proposal.md. The SDK already defines `geo.render_points` and `GeoPart`, and the runtime already transports `ui_parts` through final events. The current frontend renderer shows only a feature-count chip. The no-LLM test assistant's `geo` scenario emits a valid `GeoPart`, while its Markdown scenario shows a GeoJSON literal as text.

## Goals / Non-Goals

**Goals:** Reuse the current typed contract, make the built-in available through common runtime paths, and display the result in chat.

**Non-Goals:** Parse map data from arbitrary assistant prose or add another agent profile.

## Decisions

- ReAct and Deep add the existing built-in at tool resolution. Graph adds the same ref to its node allowlist and carries tool UI parts into the final event so chat history retains them. The point conversion runs in the SDK and works without an application tool invoker. Explicit declarations are not duplicated. An implicit ReAct tool gets a unique name if an existing provider or capability uses the default name.
- The frontend loads Leaflet only for a typed `GeoPart`. It uses Leaflet directly because `react-leaflet` has a restriction-carrying license, while Leaflet itself uses BSD-2-Clause. The existing chip is a loading and error fallback.
- GeoJSON properties become popup text through `textContent`; style values use a small validated set. The map supplies OpenStreetMap attribution with its raster tiles.
- The no-LLM assistant's `markdown` scenario replaces its raw GeoJSON block with a typed `GeoPart` using the same sample data as its `geo` scenario.

## Risks / Trade-offs

- Public OpenStreetMap tiles are an external service with usage limits. Map rendering requests tiles only when a geo part is shown; a high-volume deployment should use its own tile service or a provider suited to its traffic.
- A malformed GeoJSON feature can make Leaflet reject the layer. The renderer catches that failure and leaves the typed summary visible.

## Migration Plan

The wire contract and agent definitions do not change. Deploy the runtime and frontend together; rollback restores the existing summary chip and per-agent tool declarations.
