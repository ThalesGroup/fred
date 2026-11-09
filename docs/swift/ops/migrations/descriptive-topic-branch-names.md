---
schema: 1
title: "Use descriptive branch names without codex"
impact: none
configuration: none
configuration_reason: "Only repository contributor guidance changes; deployment configuration is unaffected."
no_action_reason: "Application code, published artifacts and deployment behavior are unchanged."
---
## Applicability

This change applies to contributors creating new branches. Existing deployments are unaffected.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Confirm new topic branches use descriptive names without `codex`.

## Rollback

Revert the contributor guidance change. No data rollback is needed.

## Limitations

Existing branch names are not changed by this guidance.
