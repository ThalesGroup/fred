---
schema: 1
title: "Keep Home search responsive while the team list is unavailable"
impact: none
configuration: none
configuration_reason: "The change only affects how Home search handles a pending or unavailable team list in the browser."
no_action_reason: "Normal frontend deployment delivers the fix. Existing team data and API responses remain compatible."
---
## Applicability

Deployments that provide Quick access search on Home.

## Prerequisites

Use the standard frontend deployment procedure.

## Configuration

Keep the existing frontend settings.

## Upgrade

Deploy the updated frontend as usual.

## Validation

In a test browser, temporarily block the bootstrap request that loads the team list and reload Home. Type in Quick access search, switch to Trending, and return to Quick access. The search field should accept input and both tabs should respond. Remove the request block and reload Home after the check.

## Rollback

Redeploy the previous frontend version using the normal rollback procedure.

## Limitations

Team-specific search results depend on the team list becoming available.
