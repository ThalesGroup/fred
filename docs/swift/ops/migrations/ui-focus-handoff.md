---
schema: 1
title: "Move focus into opened menus and panels and back to their trigger"
impact: none
configuration: none
configuration_reason: "Frontend change only; no configuration keys or defaults change."
no_action_reason: "Keyboard focus behavior of menus, popovers and drawers only; nothing to configure or migrate."
---

## Applicability

Existing deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy normally; no additional operator or user action is required.

## Validation

Open a menu with the keyboard: focus lands on its active item, and Escape returns it to the button that opened it.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
