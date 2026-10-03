---
schema: 1
title: "Plan folder-owned corpus authorization"
impact: none
configuration: none
configuration_reason: "Only OpenSpec planning documents are added; runtime and chart settings are unchanged."
no_action_reason: "This PR implements no model, API or data changes; no operator action is needed."
---
## Applicability

This documentation-only planning PR.

## Prerequisites

No additional prerequisites.

## Configuration

No configuration changes.

## Upgrade

No additional deployment action. The proposed target is not implemented here.

## Validation

Run `openspec validate simplify-corpus-authorization --strict`.

## Rollback

Revert the planning documents; there is no data migration.

## Limitations

This note does not authorize upgrading an existing deployment to the proposed
target. Its implementation and offline translation need separate impact review.
