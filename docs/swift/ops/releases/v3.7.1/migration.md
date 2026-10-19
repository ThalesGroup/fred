# Migration guide - v3.7.1

Upgrade from: `code/v3.7.0`
Operational impact: **none** (minimum version: `3.7.1`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Recover Mistral tool calls written as text in long reasoning turns

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.7.1/docs/swift/ops/migrations/3110-recover-streamed-mistral-tool-calls.md)

No API, event, data or configuration change: a Mistral tool call written as text now runs as a tool call, empty provider blocks no longer appear as text, and Mistral gets its own reasoning back in the history, once the new runtime is deployed.

See the source note for applicability, validation and rollback.

## Prepare Fred 3.7.1 release metadata and Python packages

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.7.1/docs/swift/ops/migrations/3171-prepare-fred-3-7-1.md)

The shared Python packages advance to 4.5.4 with synchronized locks and compatible dependency floors. Normal deployment is enough; this preparation adds no data migration, configuration change, re-ingestion or special restart order. The Ubuntu image note describes the separate compatibility check for custom derived images.

See the source note for applicability, validation and rollback.

## Build the Python production images on Ubuntu 24.04 LTS

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.7.1/docs/swift/ops/migrations/python-images-on-ubuntu-lts.md)

The images keep the same runtime user (UID/GID 1000), entrypoints, ports, paths and converters, so normal deployment applies them with no data migration or special restart order. Only custom images built FROM a Fred Python image need attention: they now inherit Ubuntu 24.04 instead of Debian 13, so their apt package names must be checked (for example, libmagic1 is now libmagic1t64) before rebuilding them.

See the source note for applicability, validation and rollback.
