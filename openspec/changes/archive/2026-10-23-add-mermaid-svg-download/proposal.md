## Why

Users can inspect and copy Mermaid source but cannot save the rendered diagram. Add a download action that uses the selected theme on white in a reusable vector file. This extends the Mermaid work tracked in #3252 and PR #3256.

## What Changes

- Add a translated, keyboard-accessible SVG download icon as the second inline action (fullscreen, download, copy), and alongside fullscreen exit.
- Download the complete diagram as `diagram.svg`, with a white background, the selected theme's light palette and local SVG references preserved.
- Offer the action only when the current diagram has rendered successfully. Retain the existing unframed layout, source copy and fullscreen behavior.
- Keep generation local, using the existing download helper and no new dependency.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-ui-themes`: downloadable Mermaid SVGs preserve the rendered theme outside Fred.

## Impact

Shared MermaidBlock and SVG preparation, English/French labels, component/export tests, component UX and the existing migration declaration. Continue on `codex/mermaid-themed-preview` and the existing draft PR. No backend, configuration or stored-data change.
