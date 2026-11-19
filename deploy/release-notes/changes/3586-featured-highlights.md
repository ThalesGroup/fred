---
schema: 1
title: "Show featured agent highlights on the advanced home"
impact: none
configuration: none
configuration_reason: "Only a frontend stylesheet breakpoint changes; no configuration keys or defaults change."
no_action_reason: "Existing highlights are already stored and served; the fix takes effect with a normal frontend deployment."
after: [home-featured-agents]
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

On the advanced home, with a featured agent that has highlights, verify the
highlights panel shows next to the agent description on a wide window.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Highlights are still hidden when the banner is narrower than 720px.
