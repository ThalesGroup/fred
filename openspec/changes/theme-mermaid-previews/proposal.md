## Why

Fred's shared Mermaid preview currently uses Mermaid's stock light/dark colors, independently of the active UI theme. The developer selected the beautiful-mermaid preview and requested its integration in place of the existing rendering, with colors consistent with Fred. Tracking: [#3252](https://github.com/ThalesGroup/fred/issues/3252).

## What Changes

- Use beautiful-mermaid as the preferred renderer inside the existing `MermaidBlock`, without a second product viewer or diagram-specific theme picker.
- Derive diagram colors and typography from Fred's existing semantic tokens in inline and enlarged views, including shipped and deployment themes.
- Keep official Mermaid as a compatibility fallback, preserving syntax repair, source copy, enlarged viewing, useful errors and completed-fence streaming behavior.
- Isolate generated SVG styles and IDs, retain safe rendering of untrusted diagram text and use locally supplied fonts.
- Add representative diagram fixtures and regression coverage; use existing Markdown surfaces for visual validation.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-ui-themes`: Mermaid previews inherit the active UI theme while retaining diagram compatibility and existing shared-viewer behavior.

## Impact

- Frontend: `apps/frontend/src/rework/components/shared/molecules/MermaidBlock/`, its tests, and dependency manifests. Adjust Vite dependency optimization only if required by the new renderer.
- Consumers: completed Mermaid fences rendered by the shared `MarkdownRenderer`, including chat and Help Center content. The separate JSON `MindMapBlock` is outside this change.
- Dependencies: add beautiful-mermaid and declare any directly imported SVG sanitizer; retain Mermaid for compatibility. Load diagram engines on demand.
- Documentation: update the existing component UX documentation and add the required English migration note with `impact: none`.
- No backend API, database, deployment configuration or operator migration changes. No new routing, pan/zoom feature or export format.
