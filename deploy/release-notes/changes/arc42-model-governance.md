---
schema: 1
title: "Document centralized model governance with generated architecture references"
impact: none
configuration: none
configuration_reason: "Only architecture documentation, its generation tools and CI checks change; application configuration schemas and deployment values are unchanged."
no_action_reason: "No runtime behavior, credentials or persisted data change, so operators have no additional deployment action."
---
## Applicability

Weaver architecture readers and contributors maintaining model configuration.

## Prerequisites

No additional runtime prerequisites. Documentation checks use the existing Rust,
Python and disposable Docker tooling.

## Configuration

No application or deployment configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator action is required.

## Validation

Run `make -C docs/architecture check-models` to compare generated references,
verify local links and render the model documentation diagrams. Config-schema
CI separately checks the Rust/Pydantic sources against their JSON schemas.

## Rollback

Revert the documentation and CI change if necessary; no data migration is involved.

## Limitations

These checks establish documentation freshness, not provider connectivity or
successful deployment of a particular Fred/factory revision pair.
