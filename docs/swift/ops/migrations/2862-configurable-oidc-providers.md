---
schema: 1
title: "Configure OIDC identity providers and a local user directory"
impact: minor
configuration: production
configuration_reason: "Optional OIDC provider, claim, scope, delegation and local-directory settings are exposed through the Fred chart; existing Keycloak defaults remain in effect when omitted."
---

## Applicability

Existing Fred deployments retain their Keycloak provider and directory by default. These steps also apply to operators choosing another OIDC issuer and Fred's local user directory.

## Prerequisites

Back up the Fred database and current chart values. For optional OIDC activation, register a browser client and separate confidential workload clients with the provider, grant the required API scopes and roles, and store workload credentials in deployment secrets. Confirm that the issuer's discovery document and token endpoints are reachable from Fred.

## Configuration

For an ordinary Keycloak upgrade, keep the existing provider and directory settings. To activate another issuer, set `security.user.provider` and `security.m2m.provider` to `oidc`, their `realm_url` values to the issuer URL, and `security.user_directory` to `local` consistently across the backends. Configure the API audience, browser scope, workload scope, identity and role claim paths, delegation settings and permitted origins for the provider. Use the [identity-provider guide](../../platform/IDENTITY-PROVIDERS.md) for the Entra recipe, its local configuration generator, the factory-provisioned ZITADEL profile and generic OIDC checks. Keep confidential client secrets outside chart values.

## Upgrade

Apply the control-plane Alembic migration that adds nullable user identity snapshot columns before enabling the local directory. Deploy the matching application and chart versions together. Existing Keycloak deployments can retain their configuration. For optional OIDC activation, update the provider configuration on all backends together, then restart the affected workloads and begin with a fresh browser session. Keep the issuer and identity claim stable after activation because they determine Fred user IDs.

## Validation

With the existing Keycloak configuration, sign in as platform administrator and run the platform self-test. For Entra, provide tenant and public client IDs to the local generator and set workload secrets and the 5400-second token lifetime in the environment. For ZITADEL, use the factory provisioner to generate client IDs, credentials and complete local configurations. For each optional provider, verify issuer discovery and backend startup, sign in as administrator, confirm the displayed identity and local-directory search, run the platform self-test, then check token refresh, agent document access through delegation and logout. Record the result before production rollout.

## Rollback

Restore the previous application and chart versions and the prior Keycloak configuration. Retain the additive nullable database columns during rollback; remove them only after confirming no deployed version needs local identity snapshots. Switching an activated deployment back to a previous issuer may produce different Fred user IDs and will not automatically transfer personal spaces or authorization state.

## Limitations

The local directory contains people who have signed in; it cannot create or delete accounts at the identity provider. Fred suspends a deleted local-directory user. Provider-specific refresh behavior needs validation, and changing the issuer or identity claim changes UUIDv5-derived user IDs. Manual provider walkthroughs remain required before production activation.
