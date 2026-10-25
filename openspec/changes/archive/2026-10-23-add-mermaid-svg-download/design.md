## Context

See proposal.md for motivation. MermaidBlock already owns sanitized inline/enlarged SVGs. Their styles reference Fred variables and wrapper IDs, so downloading the existing markup directly would lose colors or scoped rules. `src/utils/downloadUtils.tsx` provides `downloadFile(Blob, filename)`. The shared icon allowlist already includes `download`.

## Goals / Non-Goals

Preserve the whole diagram and selected theme on white in a standalone browser-readable SVG. PNG/PDF conversion, font embedding and a format picker are outside this change.

## Decisions

- Render a local export using an offscreen container with the current theme attributes and light mode. Use a white canvas as requested, so a dark interface cannot produce white text on a white file. Then clone the sanitized SVG and make its visual styles independent of the application before XML serialization. Preserve its natural viewBox, labels, marker/gradient references and safe HTML labels. Resolve inherited theme values, keep the wrapper scope inside the file and preserve sanitized local resource URLs. Do not mutate or replace the live preview. A screenshot would lose vector quality; serializing raw renderer output would lose inherited styling.
- Generate a local `image/svg+xml` Blob and pass it to the existing download helper as `diagram.svg`. Do not fetch assets, add a server endpoint or add a library.
- Use small icon buttons with translated native titles and accessible names as the second action in both areas. Enable export only for a successful current render; retain form-safe buttons and fullscreen focus behavior. A download failure must show localized feedback without replacing the diagram.

## Risks / Trade-offs

- Scoped styles, HTML labels and fragment references can fail outside Fred: cover both renderers and reopen downloaded files in a browser without the application styles.
- Font availability varies across computers: preserve the font stack and local fallbacks, allow safe HTML labels to overflow their foreignObject viewport rather than clipping a wider fallback font, and do not embed or fetch fonts.

## Migration Plan

Normal frontend deployment and image rollback. Update the existing impact-none migration note and PR; no operator action or stored-data conversion.
