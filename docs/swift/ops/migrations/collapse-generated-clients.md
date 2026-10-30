---
schema: 1
title: "Collapse generated OpenAPI clients in GitHub diffs"
impact: none
configuration: none
configuration_reason: "Only .gitattributes changes; no configuration key or default is involved."
no_action_reason: "The change only affects how GitHub displays generated files; no runtime code changes."
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

A pull request touching `controlPlaneOpenApi.ts` shows the file as generated and collapsed.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
