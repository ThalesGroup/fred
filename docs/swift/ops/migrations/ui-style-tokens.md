---
schema: 1
title: "Use design tokens for remaining raw radii and font sizes"
impact: none
configuration: none
configuration_reason: "Frontend change only; no configuration keys or defaults change."
no_action_reason: "Stylesheet values now come from existing design tokens and unused calendar styles are removed; nothing to configure or migrate. A few sizes change visibly, listed under Limitations."
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

Open the chat, the resources and the admin pages: corners follow the active theme and text uses the theme's type roles.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Visible changes: body text that inherits the page font is 14px instead of 12px, the knowledge base documents title uses the title-large role, and the schedule field label is weight 500.
