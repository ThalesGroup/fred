---
schema: 1
title: "Request local Keycloak login from a Fred entry URL"
impact: minor
configuration: none
configuration_reason: "Only browser login behavior changes; no Fred configuration keys, Helm values, schemas, credentials or defaults change. Optional local login can require a Keycloak Browser flow adjustment outside Fred."
---

## Applicability

Authenticated Fred deployments using Keycloak, including through generic OIDC,
with an upstream SSO configured as the default identity provider.

## Prerequisites

Normal upgrade has no new prerequisites. Optional local-login usage requires a
usable account credential in Fred's Keycloak realm and a Browser flow that allows
local authentication. The URL flag does not bypass MFA or Fred permissions.

## Configuration

Fred YAML, Helm values and generated schemas are unchanged. For optional use,
check the client's effective Browser flow in Keycloak. Duplicate a shared flow,
make the default Identity Provider Redirector and Forms alternatives, keep the
username/password execution required inside Forms, and retain required MFA and
membership checks. Preserve the default SSO alias and select the copied flow on
the intended client. See [the Keycloak guide](../../platform/KEYCLOAK.md#121-optional-local-login-when-sso-is-the-default)
for the standard Organization branch and client override location.

## Upgrade

Deploy the frontend normally. No data migration or special restart order is
needed. Optional activation can involve the Keycloak flow adjustment above,
which is why this note declares minor operational impact.

## Validation

In a private browser window, verify an ordinary Fred URL still redirects to SSO.
Open the same URL with `keycloak-login=true` and confirm Keycloak offers its
configured local authentication path. Verify the same path with a stored Fred
session and with Keycloak configured as `provider: oidc`. After successful login,
check the requested page/query/fragment, the removed flag and normal reload.

## Rollback

Restore the previous frontend. No data rollback is required. If a Keycloak flow
override was changed for optional activation, restore the previous override
separately; reverting Fred does not change Keycloak configuration.

## Limitations

Real Keycloak login depends on the server's authentication and organization
policy. Other issuers receive the explicit request but need not support
Keycloak-specific parameters. Security-disabled deployments ignore the flag.
Reopen the explicit link to retry a failed attempt; it is a one-time request.
