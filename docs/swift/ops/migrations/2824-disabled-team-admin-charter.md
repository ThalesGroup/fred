---
schema: 1
title: "Hide the team administrator charter when disabled"
impact: minor
configuration: none
configuration_reason: "No configuration key or default changes. The new authenticated bootstrap field derives from the existing app.team_admin_charter_version setting."
---
## Applicability

All Fred deployments upgrading the control-plane backend and frontend. The staged
order below matters when `app.team_admin_charter_version` is configured.

## Prerequisites

Check whether the team administrator charter is enabled. Keep the previous
frontend image available for a staged upgrade. This change needs no database
migration or data backfill.

## Configuration

Keep `app.team_admin_charter_version` as configured. An unset value continues to
disable the charter; no new setting is needed.

## Upgrade

1. If the charter is enabled, deploy the updated control-plane backend while
   keeping the previous frontend. Wait for the backend to become ready and
   confirm authenticated `GET /control-plane/v1/frontend/bootstrap` returns
   `team_admin_charter_enabled: true`.
2. Deploy the updated frontend. When the charter is disabled, the normal paired
   Fred deployment is sufficient.

## Validation

With the charter disabled, sign in as a team administrator and verify that team
settings omit Responsibilities and that its direct URL redirects to Members.
With the charter enabled, verify that eligible administrators still see
Responsibilities and pending administrators can reach the Accept action.

## Rollback

If the charter is enabled, revert the frontend before the control-plane backend
so it never relies on an absent bootstrap field. There is no data migration to
reverse.

## Limitations

A new frontend served by an old control-plane backend cannot detect an enabled
charter and temporarily hides its entry points. Pending administrators cannot
accept until the backend is updated; this is why the backend deploys first.
