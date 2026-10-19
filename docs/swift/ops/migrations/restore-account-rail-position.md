---
schema: 1
title: "Restore the account menu at the bottom of the navigation rail"
impact: none
configuration: none
configuration_reason: "Only the existing frontend shell container binding changes; no service configuration changes."
no_action_reason: "The usual frontend rebuild and deployment restores the existing layout without data or API changes."
---

## Applicability

Manager reconstruction frontend showing the account avatar near the top of the
navigation rail on business pages.

## Prerequisites

None beyond the existing frontend deployment.

## Configuration

No configuration changes.

## Upgrade

Rebuild and deploy the frontend through the ordinary Fred deployment command.

## Validation

Open Home and a team page with little content: the account menu remains at the
bottom of the navigation rail. Resize the window and check the same position.
With an announcement banner, the page fits below it without pushing the account
menu outside the window. Check the shared Profile menu still opens.

## Rollback

The previous frontend image restores the previous behavior, including the layout
regression. Data and backend contracts are unchanged.

## Limitations

This fixes shell height propagation; it introduces no new navigation or UX.
