---
schema: 1
title: "Amend platform access directory guidance"
impact: minor
after: [2965-platform-access-planning]
configuration: none
configuration_reason: "The existing security.user_directory selection now also governs platform access identity lookup; no setting or default changes."
---

## Applicability

This note amends the directory-dependent instructions in [2965-platform-access-planning.md](2965-platform-access-planning.md), specifically Upgrade steps 4 and 5 and their validation. It applies to authenticated Fred deployments using platform access, especially Keycloak deployments with completed initial imports. Follow the other instructions in note 2965 as published.

## Prerequisites

Keycloak mode requires the existing Keycloak administration service account to read users. Local mode continues using the Fred database. No database migration is required.

## Configuration

Keep the existing `security.user_directory` selection: `keycloak` for Keycloak identities, `local` for Fred's local identities. The two directories are alternative modes, not a combined directory.

## Upgrade

Deploy the updated control plane and frontend together before applying these amendments to note 2965:

1. **Step 4, Import existing users:** Before the first import, preview and import human identities from the configured directory. Keycloak mode includes accounts created directly in Keycloak and federated accounts already known to Keycloak after their first login. Local mode uses Fred's `users` table. The one-time import and removable exception behavior in note 2965 still applies. A completed import does not run again: it neither adds Keycloak accounts missed by the earlier Fred-only snapshot nor restores exceptions administrators removed. For an existing completed import, compare intended directory users with the whitelist and use **Add users** for missing exceptions before activating filtering.
2. **Step 5, Add individual exceptions:** Replace "existing Fred users" with "existing identities in the configured directory." Search and select Keycloak identities in Keycloak mode or Fred users in local mode. Individual exceptions and their identifiers remain in Fred; the whitelist displays current profiles from the selected directory. An exception whose directory profile has disappeared remains visible by its ID and can be removed. Team exceptions and their membership behavior are unchanged.
3. **Step 5, Activation review:** The population review now uses the configured directory. Review its Allowed, Blocked and Verification unavailable results before confirming as described in note 2965.

## Validation

For the amended steps 4 and 5, search for an account created directly in Keycloak but not yet used in Fred, add it to the whitelist, and confirm its current username and names appear. Confirm a federated account already known to Keycloak also appears. In local mode, confirm searches and grants use Fred users. Check the initial-import preview before the first import and the population review before activation. Unavailable directory reads must produce an error instead of an empty population. Retain the other validation checks in note 2965.

## Rollback

Roll back the control plane and frontend together. Persisted exceptions and T0 completion remain in SQL. An older control plane can display newly materialized Keycloak reference rows, but it will again use local Fred profiles and cannot find other Keycloak-only accounts.

## Limitations

The initial import is a fixed snapshot of identities returned by the selected directory, not a scan of the upstream Active Directory. Rule matches still require fresh verified claims observed by Fred; a Keycloak profile alone cannot prove them.
