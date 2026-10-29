---
schema: 1
title: "Open the team marketplace even without a collaborative team"
impact: none
configuration: none
configuration_reason: "Frontend rendering fix only; no configuration keys or defaults change."
no_action_reason: "The team marketplace page no longer redirects users who belong to no collaborative team; nothing to configure or migrate."
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

As a user who belongs to no collaborative team, open the marketplace from the navigation rail: the team marketplace page opens and lists the public teams the user can join, or an empty-state message when there are none. Personal spaces and private teams the user is not a member of are still never listed.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
