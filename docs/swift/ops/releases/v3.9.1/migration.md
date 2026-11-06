# Migration guide - v3.9.1

Upgrade from: `code/v3.9.0`
Operational impact: **none** (minimum version: `3.9.1`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Update Pillow and align Python tooling

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.9.1/docs/swift/ops/migrations/3243-pillow-and-python-tooling.md)

Normal image deployment applies the Pillow update; no data or API migration is required.

See the source note for applicability, validation and rollback.

## Remove the background gradient around the initial chat composer

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.9.1/docs/swift/ops/migrations/3250-initial-composer-gradient.md)

The UI change takes effect with normal deployment; data and APIs are unchanged.

See the source note for applicability, validation and rollback.

## Build the Python images behind TLS inspection with the host's CA bundle

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.9.1/docs/swift/ops/migrations/3253-docker-build-corporate-ca.md)

The published images are built the same way and never contain the bundle; deployments pull and run them as before.

See the source note for applicability, validation and rollback.

## Localize the agent question label in the chat trace

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.9.1/docs/swift/ops/migrations/3257-ask-user-trace-label.md)

Existing conversations render with the localized label after a normal deployment; runtime behavior, stored data and APIs are unchanged.

See the source note for applicability, validation and rollback.

## Clarify tool actions in the chat trace

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.9.1/docs/swift/ops/migrations/chat-trace-tool-labels.md)

Existing conversations, tool execution and APIs are unchanged; the new labels appear after a normal deployment.

See the source note for applicability, validation and rollback.

## MCP SDK v2 compatibility for Fred agents and Knowledge Flow

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.9.1/docs/swift/ops/migrations/mcp-v2-compatibility.md)

The existing HTTP and stdio catalogs continue to work after a normal deployment; no data or IAM migration is required.

See the source note for applicability, validation and rollback.

## Prepare Fred v3.9.1 and audit dependency updates

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.9.1/docs/swift/ops/migrations/prepare-v3-9-1-release.md)

The covered dependency update changes only the fred-sdk and fred-runtime lockfiles; normal deployment includes it.

See the source note for applicability, validation and rollback.
