---
schema: 1
title: "Build the production frontend without compiling test files"
impact: none
configuration: none
configuration_reason: "Only the frontend build TypeScript scope and Dockerfile change; no configuration keys or defaults change."
no_action_reason: "The shipped frontend bundle and runtime behavior are unchanged; only test files are excluded from the production type-check."
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

The frontend production image builds and the UI login flow works as before.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
