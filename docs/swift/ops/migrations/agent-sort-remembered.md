---
schema: 1
title: "Remember the agents page sort in the browser"
impact: none
configuration: none
configuration_reason: "Browser-side preference only; no configuration keys or defaults change."
no_action_reason: "The chosen sort is stored per browser; no server, database or configuration change."
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

On a team's agents page, choose "Latest created", leave the page and come back: the list keeps that sort.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The sort is remembered per browser and shared by every team; it does not follow the user to another device.
