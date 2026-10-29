---
schema: 1
title: "Replace \"Fred\" with \"platform\" in user-facing UI text"
impact: none
configuration: none
configuration_reason: "Only Help Center markdown and frontend translation strings change; no configuration keys or defaults change."
no_action_reason: "No data, API or configuration is touched; the new wording ships with the normal frontend deployment."
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

Open Help Center > Resources: the upload walkthrough says "the platform" (or "la plateforme" in French) instead of "Fred".

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
