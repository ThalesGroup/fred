---
schema: 1
title: "Keep team membership when the final elevated role is revoked"
impact: none
configuration: none
configuration_reason: "The role-revocation service changes behavior without adding configuration or changing defaults."
no_action_reason: "Existing team data and API request shapes remain valid; the new behavior takes effect with the normal control-plane deployment."
---
## Applicability

Existing Fred deployments upgrading the control-plane backend.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator action is required.

## Validation

In a team with another active administrator, turn off the Admin chip for a person whose only stored role is `team_admin`. Confirm the person remains in the member list with only the Member badge. The team's last active administrator must still be protected.

## Rollback

Use the normal rollback procedure. A rolled-back backend returns 409 for a sole elevated role again; people already demoted remain members through their direct `team_member` relations.

## Limitations

Concurrent attempts to remove different administrators can still race under the existing last-admin guard; issue #1985 tracks that separate fix.
