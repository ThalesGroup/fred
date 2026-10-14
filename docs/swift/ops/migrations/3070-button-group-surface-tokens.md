---
schema: 1
title: "ButtonGroup track uses design tokens only"
impact: none
configuration: none
configuration_reason: "Only the styling of the segmented button groups changes; no configuration key, chart value or permission changes."
no_action_reason: "A frontend-only styling change with no API, data or configuration effect; it applies after a normal deployment."
---
## Applicability

All Fred deployments.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Open a team's settings. The visibility and joining mode pickers show a visible
track behind their options, and only the selected option is filled. Open the
user settings: the theme and language pickers show the same, with no filled
patch behind the unselected options.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Unselected options are now transparent in every button group, so they take the
color of the track behind them; no screen keeps the former filled look.
