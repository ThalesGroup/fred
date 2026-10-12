## Why

The document-tree detail repeats dates and expands large metadata blocks inside a flat folder listing. The developer requests a compact filesystem-style tree with metadata behind document hover.

## What Changes

- Nest collapsible folders and render compact file rows without inline dates or expanded metadata blocks.
- Show available metadata in the existing rich Tooltip atom on hover and keyboard focus; support touch access.
- Keep branding, missing-date semantics, historical compatibility, displayed counts and the partial-listing warning.
- Preserve existing truncation and replace the UI warning with a discreet localized Truncated footer.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `team-resource-spaces`: move document metadata from expandable rows to document tooltips.

## Impact

DocumentTreeDetail, both locales, focused tests and component UX documentation. Payload shape remains unchanged. The character budget becomes 20,000 by default and 60,000 maximum across tool, SDK, runtime and backend. Extends #3052 / draft PR #3053; scope approved in the conversation on 2026-10-12.
