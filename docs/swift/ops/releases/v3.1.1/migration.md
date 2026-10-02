# Migration guide — v3.1.1

Upgrade from: `code/v3.1.0`
Operational impact: **none** (minimum version: `3.1.1`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Improve HITL question recovery and Other answers

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.1/docs/swift/ops/migrations/2899-hitl-question-recovery-and-other-answer.md)

No data migration is required; the additive batch resume form takes effect through normal deployment.

See the source note for applicability, validation and rollback.

## Show tool approval responses in managed chat

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.1/docs/swift/ops/migrations/2916-show-tool-approval-responses.md)

Normal frontend deployment is sufficient; existing HITL response records remain readable.

See the source note for applicability, validation and rollback.

## Prepare Fred v3.1.1 release notes and operator guide

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.1/docs/swift/ops/migrations/release-3.1.1-preparation.md)

The release notes and consolidated guide introduce no code, data, or configuration changes; normal deployment suffices.

See the source note for applicability, validation and rollback.
