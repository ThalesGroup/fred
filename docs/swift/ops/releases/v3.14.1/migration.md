# Migration guide - v3.14.1

Upgrade from: `code/v3.14.0`
Operational impact: **none** (minimum version: `3.14.1`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Render tabular query results as native chat charts

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.14.1/docs/swift/ops/migrations/3592-native-chat-charts.md)

Existing conversations and agent configurations remain valid; normal agent-pod and frontend deployment supplies the tool and renderer.

See the source note for applicability, validation and rollback.

## Prepare the Fred v3.14.1 release

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.14.1/docs/swift/ops/migrations/release-v3-14-1-preparation.md)

Normal deployment needs no additional action; the release artifacts include updated package versions, and the other notes describe the shipped application behavior.

See the source note for applicability, validation and rollback.

## Select resource rows and open folders or files with a double-click

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.14.1/docs/swift/ops/migrations/resource-name-copy-folder-row-open.md)

Existing data and APIs are unchanged; the interactions become available after normal deployment.

See the source note for applicability, validation and rollback.
