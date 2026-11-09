---
schema: 1
title: "Isolate runtime context between Graph tests"
impact: none
configuration: none
configuration_reason: "Only a test fixture changes; runtime configuration and defaults are unchanged."
no_action_reason: "Production code, stored data, and APIs are unchanged; normal deployment needs no additional action."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Run the app startup and Graph interrupted-execution tests in one pytest process; both should pass.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

This corrects test isolation only; it does not change production Graph execution.
