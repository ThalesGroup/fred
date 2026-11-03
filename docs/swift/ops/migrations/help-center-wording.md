---
schema: 1
title: "Help Center wording: conversation privacy and no product name in pages"
impact: none
configuration: none
configuration_reason: "Only Help Center Markdown pages change; no configuration keys or defaults change."
no_action_reason: "Documentation-only wording fix bundled in the frontend; data, APIs and access rules are unchanged."
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

Open the Help Center page "Teams and permissions" and check that the Member row no longer says members read the team's conversations. Open "Resources" and check that the page says "the platform" instead of the product name.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
