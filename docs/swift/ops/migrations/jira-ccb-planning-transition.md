---
schema: 1
title: "Route accepted Jira bug plans through the required CCB transition"
impact: none
configuration: none
configuration_reason: "Only repository Jira workflow instructions change; Fred deployment settings are unchanged."
no_action_reason: "The required Jira status transition does not alter Fred services, data or upgrade steps."
covers: [62d00d3d3f698fd183d75fa1a37ba931ec13c907]
---
## Applicability

Maintainers moving accepted Jira bugs from analysis to planning.

## Prerequisites

No additional deployment prerequisites.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. For an accepted bug with the approved public reply posted,
move the Jira ticket from Analysis in progress through CCB to Planned and verify
both transitions.

## Validation

Check the resulting Jira status after each transition.

## Rollback

No application or data rollback is needed for this documentation change.

## Limitations

This required intermediate transition adds no approval step for accepted bugs.
