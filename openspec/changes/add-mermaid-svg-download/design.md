## Context

See proposal.md for motivation. MermaidBlock already owns sanitized inline/enlarged SVGs. Their styles reference Fred variables and wrapper IDs, so downloading the existing markup directly would lose colors or scoped rules. `src/utils/downloadUtils.tsx` provides `downloadFile(Blob, filename)`. The shared icon allowlist already includes `download`.

## Goals / Non-Goals

Preserve the whole diagram and current theme in a standalone browser-readable SVG. PNG/PDF conversion, font embedding and a format picker are outside this change.

## Decisions

- Clone the rendered, sanitized SVG and make its visual styles independent of the application before XML serialization. Preserve its natural viewBox, labels, marker/gradient references and safe HTML labels. Resolve inherited theme values and localize any same-document resource URLs. Do not rerender or mutate the live preview. A screenshot would lose vector quality; serializing raw renderer output would lose inherited styling.
- Generate a local `image/svg+xml` Blob and pass it to the existing download helper as `diagram.svg`. Do not fetch assets, add a server endpoint or add a library.
- Use small icon buttons with translated native titles and accessible names in both action areas. Enable export only for a successful current render; retain form-safe buttons and fullscreen focus behavior. A download failure must show localized feedback without replacing the diagram.

## Risks / Trade-offs

- Scoped styles, HTML labels and fragment references can fail outside Fred: cover both renderers and reopen downloaded files in a browser without the application styles.
- Font availability varies across computers: preserve the application font stack and local fallbacks; do not embed or fetch fonts.

## Migration Plan

Normal frontend deployment and image rollback. Update the existing impact-none migration note and PR; no operator action or stored-data conversion.
