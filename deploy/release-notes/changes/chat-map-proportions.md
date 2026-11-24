---
schema: 1
title: "Correct chat map proportions"
impact: none
configuration: none
configuration_reason: "Only frontend map projection, relief image, and map height change; configuration is unaffected."
no_action_reason: "Existing data and APIs are unchanged; the corrected map takes effect with a normal frontend deployment."
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

Open a chat map with several locations in France and check that the map is no longer vertically compressed.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
