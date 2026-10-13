## Context

See proposal.md. The parser already yields redacted folder paths and document metadata. The shared Tooltip atom supports rich content, portals, viewport clamping, keyboard focus, Escape and selectable content.

## Goals / Non-Goals

Use a compact filesystem presentation without inventing missing dates. Do not fetch extra document data when a user hovers.

## Decisions

Reconstruct nesting from parsed paths, preserving document identities and folder order. Reuse Tooltip around the file row instead of a document details accordion. Keep metadata in an inset panel with a filename heading and localized arrival branding. Put the latest-displayed indication in that panel, not the file row.

## Risks / Trade-offs

Rich content must fit narrow/short viewports and remain reachable by touch and keyboard; verify actual browser interaction. Folder hierarchy is derived from the existing slash-separated corpus paths. Existing historical results remain incomplete metadata snapshots.

## Migration Plan

Normal frontend deployment and rollback. New backend results are required for new metadata; no re-ingestion or data migration.

Keep size-based truncation with a 20,000-character default and 60,000-character maximum across all existing boundaries and model-facing incomplete-listing information. Only replace the UI warning block with a small Truncated footer.

The metadata tooltip omits file creation, modification and format as requested; those fields remain available to the agent in the tool text.

Folder and file names reuse the existing --font-family-mono token; metadata labels keep the standard UI typography.
