---
schema: 1
title: "Recognize published pod chart values in migration checks"
impact: none
configuration: none
after: [agent-pod-http-route]
configuration_reason: "Only migration note validation changes; this contribution adds no deployment values or runtime settings beyond the HTTPRoute source contribution."
no_action_reason: "The validation fix changes release preparation checks only. Existing deployments need no additional upgrade action."
---
## Applicability

Release contributors declaring production configuration changes in a published
pod chart. Existing installations are unaffected by this validation fix.

## Prerequisites

No additional prerequisites for deployment.

## Configuration

No new configuration is introduced by this validation change. The optional
agent-pod route values are documented in the HTTPRoute source note.

## Upgrade

Deploy the release normally. This validation change runs during release
preparation and requires no operator action.

## Validation

Confirm migration checks accept substantive production values in the agent-pod
chart and continue to reject comment-only changes.

## Rollback

No deployment rollback action is needed for this validation change.

## Limitations

The explicit 3.7.2 version exception for optional route activation remains
documented in the separate release inclusion note.
