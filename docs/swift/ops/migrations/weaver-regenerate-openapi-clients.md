---
schema: 1
title: "Regenerate the Weaver frontend API clients"
impact: none
configuration: none
configuration_reason: "Generated frontend bindings now reflect the existing backend OpenAPI documents; no backend route or deployment configuration is changed."
no_action_reason: "This change refreshes generated source against the existing Weaver APIs and adds no data migration or operator step."
---
## Applicability

Weaver frontend builds using the current backend contracts.

## Prerequisites

No additional prerequisites beyond the normal development and deployment tooling.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator action is required.

## Validation

Run make update-all-apis in apps/frontend and confirm generated output is stable. Type-check callers separately before accepting the complete frontend migration.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

This change does not publish packages or establish end-to-end product validation.
