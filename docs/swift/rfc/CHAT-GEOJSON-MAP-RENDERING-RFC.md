# RFC: GeoJSON Map Rendering in Chat (CHAT-13)

**Status:** Implemented (2026-06-24) — live pod validation pending
**Author:** Vanshaj Behl
**Date:** 2026-06-24
**ID:** CHAT-13
**Backlog:** `docs/swift/backlog/CHAT-UI-BACKLOG.md` (new section — GeoJSON map rendering)
**Parent RFC:** `docs/swift/rfc/CHAT-RENDERING-SPEC.md`
**Related:** `docs/swift/rfc/STREAMING-RENDER-GUARD-RFC.md` (CHAT-09) — see §3.4
**Contract impact:** none — frontend only

---

## 1. Problem

Agent replies frequently contain geographic data as a GeoJSON `FeatureCollection`.
Today that data renders as a raw ` ```json ` code block: a wall of coordinates the
user has to read by hand. The chat renderer already turns two other fenced payloads
into rich visualizations — ` ```mermaid ` → flowchart (`MermaidBlock`) and
` ```mindmap-json ` → interactive mindmap (`MindMapBlock`) — but there is no
equivalent for maps.

We want GeoJSON to render as an interactive map (Leaflet), consistent with the
existing mermaid/mindmap treatment, and we want this to be a **renderer capability
available to every agent**, not a one-off for the test assistant's hardcoded
`markdown` scenario.

### 1.1 Why not the `ui_parts` / `GeoPart` path

The SDK already defines a `GeoPart` (`libs/fred-sdk/fred_sdk/contracts/context.py`)
that an agent can emit in `ui_parts` on the `final` event. An earlier attempt at
this feature rendered maps from that structured part. It was rejected for this use
case because:

- It only fires when an agent deliberately emits a `GeoPart`. The actual content
  users see today — including the test assistant's `markdown` scenario — embeds
  GeoJSON **inside the markdown text** as a ` ```json ` fence, which the `ui_parts`
  path never touches.
- It requires every agent to adopt a new emission pattern to get maps, whereas
  mermaid/mindmap "just work" from markdown content.

`STREAMING-RENDER-GUARD-RFC.md §1.3` explicitly scoped GeoJSON out, on the
assumption it would always arrive as a `GeoPart`. This RFC revisits that: GeoJSON
in a markdown fence is the common case and should render as a map.

The `GeoPart`/`ui_parts` path remains valid and is **not removed** — it is simply
not the mechanism used here.

---

## 2. Proposed solution

### 2.1 Principle

Add one branch to the `MarkdownRenderer` fenced-code dispatch, alongside the
existing `mindmap`/`mermaid` branches, that routes GeoJSON to a new `GeoMapBlock`
molecule rendering an interactive Leaflet map.

### 2.2 Detection rule

| Fence | Rendered as | Rule |
|---|---|---|
| ` ```geojson ` | `GeoMapBlock` | Always — explicit opt-in |
| ` ```json ` | `GeoMapBlock` | Only when the body parses as a GeoJSON `FeatureCollection` |
| ` ```json ` (non-geo) | `CodeBlock` | Falls through unchanged |

The `json` case is intentionally conservative: it parses the fence and checks
`type === "FeatureCollection"`. Anything else (plain JSON, a bare `Feature`,
invalid JSON) falls through to the normal `CodeBlock`, so no existing behavior
regresses. The detector (`isGeoJsonFeatureCollection`) is a pure function exported
from `GeoMapBlock` and is unit-testable without a DOM.

### 2.3 `GeoMapBlock` molecule

Mirrors `MindMapBlock`'s shape — a self-contained molecule taking
`{ code, language }`, parsing the fence, and rendering. Stack:
`react-leaflet` (`MapContainer` + OpenStreetMap `TileLayer` + `GeoJSON`).
Dependencies (`leaflet`, `react-leaflet`, `@types/leaflet`) are already in
`package.json`; this is their first consumer.

Behavioral decisions:

- **Points → SVG pin via `L.divIcon`.** Leaflet's default PNG marker icons
  (`marker-icon.png` etc.) do not survive Vite bundling and render as broken
  images. An inline-SVG teardrop pin has no external asset and always renders.
  (A `circleMarker` variant was also tried; the SVG pin matches the familiar
  Leaflet look from leafletjs.com and is unambiguous to users.)
- **Polygons / lines** are styled from the feature's `color` / `fillOpacity`
  properties, falling back to the theme `--primary` token.
- **Popups** bind the feature's `name` / `title` property.
- **Auto-fit** to the data's bounds via a small `FitBounds` child (`useMap` +
  `L.geoJSON(data).getBounds()`), falling back to a central-Europe view when the
  bounds are not resolvable.

### 2.4 Layout / stacking

Two CSS rules in `GeoMapBlock.module.css`:

- **Landscape aspect** (`height: 20rem`, `width: 100%`) so the map is a wide
  rectangle like leafletjs.com, not a tall square.
- **Own stacking context** (`position: relative; z-index: 0`) on the Leaflet
  container. Leaflet assigns internal pane/control z-indices up to 1000; without
  a containing stacking context these escape to page level and overlap the
  floating chat input bar (`.inputOverlay`, `z-index: 1`) on scroll. Confining
  them to a `z-index: 0` context keeps the whole map below the input bar.

---

## 3. Alternatives considered

### 3.1 Structured `GeoPart` in `ui_parts` (rejected for this use case)

Render maps from an agent-emitted `GeoPart` on the `final` event, plumbed through
`ThreadMessage` → `AssistantTurn`. **Rejected:** does not render GeoJSON that lives
in markdown text (the common case), and forces every agent to adopt a new emission
pattern. Not removed from the platform — just not the mechanism here. See §1.1.

### 3.2 Leaflet default PNG markers (rejected)

Use `L.Icon.Default` with the bundled `leaflet/dist/images/*.png` URLs.
**Rejected:** still rendered as broken images in the Vite build (a well-known
Leaflet+bundler asset-path problem). The inline-SVG `divIcon` removes the external
asset dependency entirely.

### 3.3 `circleMarker` for points (rejected)

Draw points as SVG circles. **Rejected:** works and needs no assets, but reads as
a faint dot rather than a recognizable location marker; the SVG pin is clearer and
matches user expectation from the official Leaflet page.

### 3.4 Render all ` ```json ` fences as maps (rejected)

**Rejected:** would break every non-geographic JSON snippet. The
`FeatureCollection` discriminator keeps detection safe.

---

## 4. Files touched

| File | Change |
|---|---|
| `apps/frontend/src/rework/components/shared/molecules/GeoMapBlock/GeoMapBlock.tsx` | New molecule — parse + Leaflet map + SVG-pin points + fit-bounds; exports `parseFeatureCollection` / `isGeoJsonFeatureCollection` |
| `apps/frontend/src/rework/components/shared/molecules/GeoMapBlock/GeoMapBlock.module.css` | New — landscape sizing, stacking context, `.pin` (strip default divIcon box), error state |
| `apps/frontend/src/rework/components/shared/molecules/MarkdownRenderer/MarkdownRenderer.tsx` | Add the `geojson` / GeoJSON-`json` branch to the fenced-code dispatch |

No backend changes. No contract changes. No new dependencies (Leaflet already
present).

---

## 5. Acceptance criteria

### 5.1 Functional

- [ ] Sending `markdown` to the test assistant renders the "GeoJSON (map)" section
  as an interactive Leaflet map instead of a JSON code block.
- [ ] Point features show as visible location pins (no broken-image boxes); clicking
  a pin opens a popup with the feature `name`.
- [ ] Polygon features render styled from their `color` / `fillOpacity` properties.
- [ ] The map auto-fits to show all features.
- [ ] On scroll, the map slides **behind** the chat input bar (no overlap).
- [ ] The map is a landscape rectangle, not a square.
- [ ] A non-geographic ` ```json ` fence still renders as a normal code block.
- [ ] An explicit ` ```geojson ` fence from any agent renders as a map.

### 5.2 Unit tests (`GeoMapBlock.test.ts`)

| Input | `isGeoJsonFeatureCollection` |
|---|---|
| Valid `FeatureCollection` JSON | `true` |
| Valid JSON object without `type: "FeatureCollection"` | `false` |
| A bare `Feature` | `false` |
| Invalid JSON | `false` |

### 5.3 Non-regression

- [ ] `make -C apps/frontend code-quality` passes (`tsc --noEmit` + prettier).
- [ ] Existing CHAT-RENDERING-SPEC §5 acceptance criteria still pass.
- [ ] `make -C apps/frontend build` succeeds with Leaflet bundled (first consumer).
