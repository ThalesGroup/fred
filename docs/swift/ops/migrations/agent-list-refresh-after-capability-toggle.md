---
schema: 1
title: "Refresh agent lists after a capability is enabled or disabled"
impact: none
configuration: none
configuration_reason: "Frontend cache invalidation only; no configuration keys or defaults change."
no_action_reason: "The admin capabilities page now refreshes the affected agent lists by itself."
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

Disable a capability used by an agent for one team on the admin capabilities page, then open that team's agents: the agent shows as suspended without reloading the page.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Other open browser sessions still refresh on their next load, as before.
