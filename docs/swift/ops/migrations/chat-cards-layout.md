---
schema: 1
title: "Show the chat and its side panels on separate cards, with the launcher rail outside them"
impact: none
configuration: none
configuration_reason: "Only frontend components and stylesheets change."
no_action_reason: "The change ships with the normal deployment and stores no new data."
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

Open a conversation and a side panel: the panel sits on its own card beside the chat, and the launcher rail stays at the far right, outside the cards.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
