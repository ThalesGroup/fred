---
schema: 1
title: "Whitelist people by email before their first sign-in, and clean up redundant exceptions"
impact: minor
configuration: local
configuration_reason: "libs/fred-pod/fred_pod/security/structure.py only gains the token-derived KeycloakUser.email_verified field, read from the existing email_verified claim; no configuration key, chart value or permission changes, so production values are unaffected."
---
## Applicability

Fred deployments with platform access filtering available (authenticated, ReBAC enforced).

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

1. Run the control-plane database migration (`make db-upgrade` in `apps/control-plane-backend`, or the chart's migration hook). It creates `platform_access_pending_emails`.
2. Then roll out the backends. Knowledge Flow and the agent backends check for this table at startup, like the other platform access tables, and refuse to start without it.

Existing exceptions, rules and teams are unchanged.

## Validation

In Platform access > Users, add an email that no user has yet: it appears under the "Pending" filter. Sign in with that verified email while filtering is on: access is granted and the person moves to the whitelist table.

## Rollback

Use the normal rollback procedure. The downgrade drops `platform_access_pending_emails`; emails still waiting are lost, while exceptions already created from them remain.

## Limitations

An email entry only matches a token whose email claim equals it and which does not carry `email_verified: false`.
