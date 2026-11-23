---
schema: 1
title: "Follow the UI theme in chat maps"
impact: none
configuration: none
configuration_reason: "Only frontend map colors and theme handling change; no deployment settings or defaults change."
no_action_reason: "Existing conversations and GeoPart data are unchanged; maps use the current palette after a normal deployment."
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

Open a chat map, switch between light and dark mode in preferences, and check that the open map changes colors without losing its center or zoom.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
