# Migration guide - v3.18.1

Upgrade from: `code/v3.18.0`
Operational impact: **none** (minimum version: `3.18.1`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Prepare Fred v3.18.1 release inputs and dependency locks

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.18.1/docs/swift/ops/migrations/prepare-v3-18-1-release.md)

The dependency lock refresh and release inputs require no data migration or special upgrade step; the Word preview fix takes effect with a normal image rollout.

See the source note for applicability, validation and rollback.

## Install LibreOffice Writer for Word template PDF previews

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.18.1/docs/swift/ops/migrations/word-template-pdf-preview-writer.md)

A normal image rollout installs Writer; no data migration or special deployment step is needed.

See the source note for applicability, validation and rollback.
