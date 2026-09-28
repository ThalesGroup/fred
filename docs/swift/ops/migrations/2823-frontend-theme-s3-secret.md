---
schema: 1
title: "Create theme S3 Secret only when the frontend theme is configured"
impact: none
configuration: production
configuration_reason: "Fred chart values now explicitly default frontend extraEnvVars to an empty list; the template uses its FRONTEND_THEME_URL entry to decide whether to render the Secret. Existing overlays and activation remain compatible."
no_action_reason: "Deployments with a configured frontend theme and both storage keys retain the Secret; deployments without a theme only lose an unused Secret during normal deployment."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required. `applications.frontend.extraEnvVars` continues to hold `FRONTEND_THEME_URL` for deployments that use a theme.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Render the chart with content-storage credentials and no frontend theme URL; verify `s3-credentials` is absent. With a nonempty theme URL and both credentials, verify the Secret is present.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

A theme URL injected through `valueFrom` is treated as configured at chart render time; the chart cannot inspect its runtime value.
