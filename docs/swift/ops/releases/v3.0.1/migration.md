# Migration guide — v3.0.1

Upgrade from: `code/v3.0.0`
Operational impact: **none** (minimum version: `3.0.1`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Run a team prompt from the chat by typing a command

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.0.1/docs/swift/ops/migrations/prompt-commands.md)

The additive schema migration runs as part of normal deployment; existing prompts and conversations remain compatible, with no configuration, re-ingestion, or additional operator action required.

See the source note for applicability, validation and rollback.

## Prepare the Fred 3.0.1 release documents

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.0.1/docs/swift/ops/migrations/release-3-0-1-preparation.md)

Release documentation introduces no runtime or data change; the prompt-command migration is covered by its own note.

See the source note for applicability, validation and rollback.
