---
schema: 1
title: "Reserve Jira bug resolution for confirmed production deployment"
impact: none
configuration: none
configuration_reason: "Only repository instructions for handling Jira tickets change; Fred deployment settings are unchanged."
no_action_reason: "Ticket workflow guidance changes no running service, stored application data or upgrade procedure."
covers: [ee83302190cd3779786db4401993893c4dce18aa]
---
## Applicability

Maintainers handling Jira bug reports after this release.

## Prerequisites

No additional deployment prerequisites.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. Keep a bug ticket Planned while its fix is developed or
tagged; mark it Resolved after confirmed deployment on the reporter's production
platform, then Closed after independent verification.

## Validation

Review the Jira skill's bug status table before transitioning a ticket.

## Rollback

No application or data rollback is needed for this documentation change.

## Limitations

Production deployment confirmation remains a manual developer check.
