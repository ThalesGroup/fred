## 1. Shared map tool

- [x] 1.1 Add an optional zone argument and validate three distinct coordinates; verify invalid calls return a tool error without a UI part in focused SDK tests.
- [x] 1.2 Emit a closed GeoJSON polygon alongside the original point features only when requested; verify point-only and zone coordinates in focused SDK tests.

## 2. Agent guidance and rendering

- [x] 2.1 Explain zone requests and point order in the available-tools description; verify the prompt test keeps this guidance out of platform instructions.
- [x] 2.2 Verify the existing Leaflet renderer displays the polygon and retains markers, labels, and the location list in a focused frontend test.

## 3. Documentation and integration

- [x] 3.1 Update the SDK and migration documentation for optional zones; verify the text describes default point behavior and the existing offline map.
- [x] 3.2 Run the relevant SDK, runtime prompt, and frontend checks; review the branch diff and verify the generic built-in tool contract is unchanged.
