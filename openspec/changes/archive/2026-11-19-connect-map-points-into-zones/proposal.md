## Why

Agents can already place GPS coordinates found in Fred corpus documents on a chat map, but the shared geo tool cannot connect selected points into a boundary. Users need to request a zone while keeping the normal point-only map as the default.

## What Changes

- Add an optional zone mode to `geo.render_points`. It closes the supplied points in their given order into one GeoJSON polygon while keeping each point marker.
- Require at least three distinct coordinates for a zone. Invalid calls return a correctable tool error without a map part.
- Explain the optional mode and the required point order in the tool's available-tools description. Agents with corpus access continue to use existing document search to obtain coordinates.
- Show the polygon in the existing offline Leaflet map and keep its name in the location list.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `chat-geo-rendering`: Optional closed zones assembled from selected GPS points, with point-only rendering as the default.

## Impact

`libs/fred-sdk` tool arguments and GeoJSON generation, the geo renderer and its tests in `apps/frontend`, the existing geo specification, and user-facing tool guidance. `GeoPart`, the generic `BuiltinToolSpec`/`LOCAL` runtime contract, corpus search, and the bundled offline basemap remain unchanged. This extends the current draft PR #3591 and issue #3590.
