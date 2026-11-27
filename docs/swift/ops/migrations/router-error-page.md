---
schema: 1
title: "Improve the router error page"
impact: none
configuration: none
configuration_reason: "Only frontend error presentation and translations change; no configuration keys or defaults change."
no_action_reason: "Existing data and APIs are unchanged; the new page appears with a normal frontend deployment."
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

Open a route whose component throws during render and confirm the localized error card shows reload and Home actions without a raw exception.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The page handles errors caught by React Router. Errors before the router renders are outside this change.
