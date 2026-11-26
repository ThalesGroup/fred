## Decisions

- **Description on every turn**, not read by a tool on demand: in the spike the agent invented instead of searching. *Rejected:* a tool re-asking the vision model (new confident errors).
- **Limits note before the description**, so truncation cuts the description, never the note.
- **One budget for all images** (30 000 characters, most recent first). *Rejected:* a per-image cap.
- **SVG through the existing renderers** (LibreOffice to PDF, PDFium page 1, as PPTX ingestion). *Rejected:* an SVG rasterizer (new dependency).
- **Sanitize, bound, then render best-effort:** defusedxml, small internal entities only, no active elements or external references, raster `data:` only when Pillow identifies it (25 MP max), canvas fitted to 1568 px, two renders per process, 30 s slot wait. Any failure keeps the facts.

## Risks / Trade-offs

- [Vision models misread diagrams] → the agent cites its source; SVG facts carry the reliable part; a stronger model is configuration.
- [The ingestion vision model is global, not team-routed] → follow-up if needed.
