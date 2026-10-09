## Why

The frontend already downloads a deployment theme ZIP from an S3-compatible store such as SeaweedFS, but only images and Markdown are read. Operators need the same ZIP to carry CSS overrides and the existing frontend branding labels and asset names.

## What Changes

- Accept `theme-custom.css`, a strictly allowlisted `theme-properties.json`, and English/French translation overrides in the ZIP.
- Apply CSS before application content is painted and merge branding properties before frontend startup.
- Keep the existing SeaweedFS URL, bounded download, archive path restrictions, stock fallback and restart-to-activate model.
- Extend the sample bundle, documentation and container smoke checks.

Out of scope: browser editor, upload API, database persistence and hot reload of connected clients.

## Impact

Frontend entrypoint, static bootstrap and theme bundle helper. No backend API or database migration.
