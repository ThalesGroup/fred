---
schema: 1
title: "Show the import count badge in the Resources panel"
impact: none
configuration: none
configuration_reason: "Only frontend CSS changes; no configuration keys or defaults change."
no_action_reason: "The badge layout changes with the normal frontend deployment; data and APIs are unchanged."
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

Open Resources while files are being imported and check that the count badge is fully visible on the panel button.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
