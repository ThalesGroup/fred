---
schema: 1
title: "Show the deployment's site name instead of \"Fred\" in user-facing UI text"
impact: none
configuration: none
configuration_reason: "Help Center pages and translations now read the existing siteDisplayName branding property; no configuration key or default changes."
no_action_reason: "Deployments without siteDisplayName keep showing Fred; branded ones show their name with the normal frontend deployment."
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

On a deployment whose branding sets `siteDisplayName`, open Help Center > Getting started: the welcome page names that site instead of "Fred".

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
