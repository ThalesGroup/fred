# Proposal

## Why

Fred users normally authenticate through Keycloak's default upstream SSO. Administrators who need local Keycloak credentials currently have to edit a generated authorization URL, preserving its state and PKCE parameters by hand.

## What Changes

- Accept `?keycloak-login=true` on any Fred entry URL with browser security enabled, for both `provider: keycloak` and `provider: oidc`. Keycloak connected through generic OIDC supports the same request parameters.
- Start one interactive OIDC authorization with `kc_idp_hint=` and `prompt=login`, including when Fred has a stored authenticated session.
- Consume the flag before redirecting and preserve the requested local path, other query parameters and hash through the existing callback state. Reloading the returned page must not force another login.
- Preserve ordinary sign-in without the flag for both provider settings, plus insecure mode, refresh, logout, admission and authorization behavior. No provider setting or issuer detection gates the explicit flag.
- Document the entry URL and prerequisite Keycloak browser flow/local credentials. No new route, login button, backend setting or dependency.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-oidc-login`: add an explicit, one-time Keycloak local-login request. Reuse the capability defined in `add-identity-provider-portability/specs/frontend-oidc-login/spec.md`; its implementation merged through #2863, while its parent change still awaits manual verification and specification sync. This follow-up adds a requirement without duplicating the existing lifecycle requirements or reopening that closed issue.

## Impact

- Code: `apps/frontend/src/security/OidcBrowserSession.ts`, behind the existing `KeyCloakService` facade.
- Verification: `apps/frontend/src/security/OidcBrowserSession.test.ts` and existing facade regression tests; exercise actual SDK authorization URL serialization and callback restoration.
- Guidance: `docs/swift/platform/KEYCLOAK.md` and an operator migration note explaining optional usage and Keycloak prerequisites.
- Tracking: [#3133](https://github.com/ThalesGroup/fred/issues/3133).
- No API/schema, deployment configuration or Keycloak server configuration is changed by Fred. The URL grants no role or permission.
