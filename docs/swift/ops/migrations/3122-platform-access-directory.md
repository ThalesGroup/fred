---
schema: 1
title: "Use the configured user directory for platform access"
impact: minor
configuration: none
configuration_reason: "The existing security.user_directory selection now also governs platform access identity lookup; no setting or default changes."
---

## Applicability

Authenticated Fred deployments using platform access, especially Keycloak deployments with completed initial imports.

## Prerequisites

Keycloak mode requires the existing Keycloak administration service account to read users. Local mode continues using the Fred database. No database migration is required.

## Configuration

Keep the existing `security.user_directory` selection: `keycloak` for Keycloak identities, `local` for Fred's local identities. The two directories are alternative modes, not a combined directory.

## Upgrade

Deploy the updated control plane and frontend together. Individual exceptions remain in Fred and their identifiers are unchanged. The whitelist now displays profiles from the selected directory; an exception whose profile is no longer present remains visible by its ID and can be removed.

A previously completed initial import stays completed. It does not automatically import Keycloak accounts that were missed by the old Fred-only snapshot, and it does not restore exceptions administrators removed. On such installations, compare the current directory's intended users with the whitelist and use the ordinary Add users action for any missing exceptions before activating filtering. Keycloak identities that are not yet known to Keycloak remain outside the initial snapshot.

## Validation

In Keycloak mode, search for an account created directly in Keycloak but not yet used in Fred, add it to the whitelist, and confirm its current username and names appear. Confirm a federated account already known to Keycloak also appears. In local mode, confirm searches and grants use Fred users. Check the initial-import preview before first activation and confirm unavailable directory reads produce an error instead of an empty population.

## Rollback

Roll back the control plane and frontend together. Persisted exceptions and T0 completion remain in SQL. An older control plane can display newly materialized Keycloak reference rows, but it will again use local Fred profiles and cannot find other Keycloak-only accounts.

## Limitations

The initial import is a fixed snapshot of identities returned by the selected directory, not a scan of the upstream Active Directory. Rule matches still require fresh verified claims observed by Fred; a Keycloak profile alone cannot prove them.
