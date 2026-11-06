# Migration guide - v3.9.2

Upgrade from: `code/v3.9.1`
Operational impact: **none** (minimum version: `3.9.2`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Add selected-tree downgrade for agent pod migrations

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.9.2/docs/swift/ops/migrations/3224-runtime-capability-downgrade.md)

Normal deployment still runs the existing upgrade command. The new downgrade command is an optional operator maintenance action.

See the source note for applicability, validation and rollback.

## Patch aiohttp and pypdf, and publish the Python libraries against PyPI

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.9.2/docs/swift/ops/migrations/aiohttp-pypdf-security-floors.md)

The patched aiohttp and pypdf ship inside the rebuilt images through their locks, so a normal deployment applies them.

See the source note for applicability, validation and rollback.

## Prepare Fred v3.9.2 and audit dependency updates

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.9.2/docs/swift/ops/migrations/prepare-v3-9-2-release.md)

The covered dompurify and KaTeX updates ship inside the rebuilt frontend image; normal deployment includes them.

See the source note for applicability, validation and rollback.

## Advance the shared Python libraries to 4.5.9 for v3.9.2

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.9.2/docs/swift/ops/migrations/prepare-v3-9-2-shared-libraries-4-5-9.md)

fred-runtime 4.5.8 was published before the runtime and capability downgrade command (#3225) merged; 4.5.9 ships it, and normal deployment includes it.

See the source note for applicability, validation and rollback.
