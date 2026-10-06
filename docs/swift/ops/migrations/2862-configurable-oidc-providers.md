---
schema: 1
title: "Configure OIDC identity providers and a local user directory"
impact: minor
after: [2972-configurable-gcu-versions]
configuration: production
configuration_reason: "Optional OIDC provider, claim, scope, delegation and local-directory settings are exposed through the Fred chart; existing Keycloak defaults remain in effect when omitted."
---

## Applicability

Existing Fred deployments retain their Keycloak provider and directory by default. These steps also apply to operators choosing another OIDC issuer and Fred's local user directory.

## Prerequisites

Back up the Fred database and current chart values. For optional OIDC activation, register a browser client and separate confidential workload clients with the provider, grant the required API scopes and roles, and store workload credentials in deployment secrets. Confirm that the issuer's discovery document and token endpoints are reachable from Fred. For local-directory deployments, select an OpenFGA model supporting `suspended: [user]` on `organization:fred` before starting the services, even when delegation is disabled.

## Configuration

For an ordinary Keycloak upgrade, keep the existing provider and directory settings. To activate another issuer, set `security.user.provider` and `security.m2m.provider` to `oidc`, their `realm_url` values to the issuer URL, and `security.user_directory` to `local` consistently across the backends. Configure the API audience, browser scope, workload scope, identity and role claim paths, delegation settings and permitted origins for the provider. Use the [identity-provider guide](../../platform/IDENTITY-PROVIDERS.md) for the Entra recipe, its local configuration generator, the factory-provisioned ZITADEL profile and generic OIDC checks. Keep confidential client secrets outside chart values.

## Upgrade

Follow the [coordinated database upgrade](2972-configurable-gcu-versions.md), which includes the nullable identity snapshot columns, before enabling the local directory. Deploy the matching application and chart versions together. Existing Keycloak deployments can retain their configuration. For optional OIDC activation, update the provider configuration on all backends together, then restart the affected workloads and begin with a fresh browser session. Keep the issuer and identity claim stable after activation because they determine Fred user IDs.

## Validation

With the existing Keycloak configuration, sign in as platform administrator and run the platform self-test. For Entra, provide tenant and public client IDs to the local generator and set workload secrets and the 6000-second token lifetime in the environment. For ZITADEL, use the factory provisioner to generate client IDs, credentials and complete local configurations. For each optional provider, verify issuer discovery and backend startup, sign in as administrator, confirm the displayed identity and local-directory search, run the platform self-test, then check token refresh, agent document access through delegation and logout. Delete a disposable local-directory person with delegation disabled and verify that their existing bearer is refused on the next request while an active bystander retains access. Provider accounts and memberships remain stored. Disabled suspension returns 403 `account_suspension_disabled`; unavailable account-status checks return 503 `account_status_unavailable`. For username-based imports, check that referenced local usernames resolve uniquely. A known collision fails preflight with `ambiguous_username` before bundle SQL/OpenFGA writes; update the conflicting profiles against the provider before retrying. Unrelated collisions do not block the bundle. Record the result before production rollout.

For both Keycloak and generic OIDC, verify that a definitive renewal refusal (such as `invalid_grant`) clears the live credentials and stored OIDC user; reload must require sign-in. During a transient provider outage or timeout, an unexpired bearer remains available and renewal can be retried. No late response may replace a newer accepted session. Storage cleanup failure revokes the current in-memory session; it cannot guarantee persistent removal while browser storage is unavailable.

## Rollback

A provider-only rollback can restore the prior Keycloak configuration while keeping the v3.2.0 application and chart. For a full rollback to v3.1.1, follow the [coordinated rollback](2972-configurable-gcu-versions.md), including its CGU downgrade guard, before restarting old readers. Nullable identity snapshot columns can remain only if the selected database rollback target retains them; a full reverse migration chain drops them. Switching an activated deployment back to a previous issuer may produce different Fred user IDs and will not automatically transfer personal spaces or authorization state.

## Limitations

The local directory contains people who have signed in; it cannot create or delete accounts at the identity provider. Fred suspends a deleted local-directory user. Snapshots can become stale after a rename; collision rejection does not verify current ownership of a username that appears unique. Provider-specific refresh behavior needs validation, and changing the issuer or identity claim changes UUIDv5-derived user IDs. Manual provider walkthroughs remain required before production activation.
