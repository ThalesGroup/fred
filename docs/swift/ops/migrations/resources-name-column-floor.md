---
schema: 1
title: "Keep document names visible beside the import panel"
impact: none
configuration: none
configuration_reason: "Only the frontend Resources table layout changes; no configuration keys or defaults change."
no_action_reason: "Layout-only frontend change; it applies with the normal frontend deployment."
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

Open Team Resources, open the import panel and widen it: document and folder names and each row's more button stay visible.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

On narrow windows the size, date, author and status columns shrink and truncate first.
