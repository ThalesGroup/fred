## Context

See proposal.md. The SDK already defines `geo.render_points` and `GeoPart`, and the runtime already transports `ui_parts` through final events. The current frontend renderer shows only a feature-count chip. The no-LLM test assistant's `geo` scenario emits a valid `GeoPart`, while its Markdown scenario shows a GeoJSON literal as text.

## Goals / Non-Goals

**Goals:** Reuse the current typed contract, make the built-in available through common runtime paths, and display the result in chat.

**Non-Goals:** Parse map data from arbitrary assistant prose or add another agent profile.

## Decisions

- ReAct and Deep add the existing built-in at tool resolution. Graph adds the same ref to its node allowlist and carries tool UI parts into the final event so chat history retains them. The point conversion runs in the SDK and works without an application tool invoker. Explicit declarations are not duplicated. An implicit ReAct tool gets a unique name if an existing provider or capability uses the default name.
- The frontend bundles Leaflet with the chat renderer. It uses Leaflet directly because `react-leaflet` has a restriction-carrying license, while Leaflet itself uses BSD-2-Clause. The existing chip is an error fallback.
- GeoJSON properties become popup text through `textContent`; style values use a small validated set. A bundled Natural Earth 1:110m country layer supplies geographic context without remote requests. The map displays Natural Earth attribution. The dataset is public domain (version 5.1.1) and is simplified for global context; streets are outside its scope.
- The no-LLM assistant's `geo` scenario invokes the shared tool so its call and result are visible. Its `markdown` scenario replaces its raw GeoJSON block with a typed `GeoPart`.

## Risks / Trade-offs

- The compact offline basemap shows countries and borders, not street-level detail. Leaflet and the bundled world data load with the chat renderer so a later map needs no additional network request.
- A malformed GeoJSON feature can make Leaflet reject the layer. The renderer catches that failure and leaves the typed summary visible.

## Migration Plan

The wire contract and agent definitions do not change. Deploy the runtime and frontend together; rollback restores the existing summary chip and per-agent tool declarations.
