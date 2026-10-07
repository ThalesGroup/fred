---
schema: 1
title: "Sidebar rail and nav panel, denser agents, prompts and resources pages"
impact: none
configuration: none
configuration_reason: "Frontend layout and styles only; no configuration keys or defaults change."
no_action_reason: "The new layout ships with the frontend image; no operator or user step is needed."
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

Open the application: the left sidebar shows a narrow icon rail with the user
avatar at its bottom, next to a navigation panel card. On the resources page,
the usage statistics open from an icon button in the page header, and the
table search field is compact.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
