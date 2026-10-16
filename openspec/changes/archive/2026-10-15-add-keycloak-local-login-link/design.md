# Design

## Context

See proposal.md for motivation and the existing frontend-oidc-login capability for the common browser lifecycle. `OidcBrowserSession.login()` processes callbacks, restores a stored user, then redirects only if necessary. It already keeps the requested path/query/hash in local OIDC state. The installed SDK serializes empty `extraQueryParams` values, so `kc_idp_hint: ""` produces the required `kc_idp_hint=`.

## Goals / Non-Goals

- Keep state, PKCE S256, scopes, registered callback URI and local return-destination validation owned by the existing OIDC lifecycle.
- Add no endpoint, router branch, new configuration field or persistent login mode. The flag cannot grant Fred admission, organization membership or roles.

## Decisions

### Use an exact, one-time query flag

Recognize `keycloak-login=true` for both configured provider settings, `keycloak` and `oidc`, only on an initial entry after handling any OIDC callback. The flag explicitly requests Keycloak-compatible authorization parameters; a Keycloak server configured through generic OIDC understands them identically. Do not detect issuer URL shapes or retain a provider check for this option. A query flag works on existing routes and hosted base paths without changes to routing or server rewrites. A dedicated `/keycloak-login` route adds a second entry contract and needs a return-target convention, so it is excluded.

Consume the flag with URLSearchParams before redirecting; keep the path, other query parameters and hash in local request state. Clean the current history entry as well, preserving its existing history state. Persist no preference in localStorage, sessionStorage or global client settings. A failed attempt can be retried by reopening the explicit link. Insecure mode does not interpret the flag.

### Request interactive authentication through the common SDK

Use the common OIDC browser session without a provider-specific branch. The explicit request takes precedence over restoring or refreshing a stored Fred user: clear the previous local OIDC user and live bearer before redirecting. Retain generation/invalidation safeguards against late callbacks and renewal results. Do not call provider logout, which would end upstream SSO sessions unnecessarily.

Call the existing `signinRedirect` with the cleaned return path as `state`, `prompt: "login"` and `extraQueryParams: { kc_idp_hint: "" }`. These options apply to this request only. Do not concatenate authorization URLs or forward arbitrary application query parameters. Existing callback/error processing runs first, so callback handling cannot trigger a forced-login loop.

### Reuse tests and operator guidance

Extend `OidcBrowserSession.test.ts`. Verify actual SDK URL serialization with OidcClient, opaque state, PKCE S256, a stored-user switch, callback restoration, removed flag and reload for both provider configurations. Retain invitation-token privacy and normal-login/refresh/logout coverage. Document usage in KEYCLOAK.md, including generic OIDC configuration, with the browser-flow prerequisite discovered in this session; keep requirements authoritative in the delta spec.

## Risks / Trade-offs

- Keycloak can still reject local login or route through organization identity-first login depending on its flow. Document that the default redirector and outer organization/forms branches must allow fallback and local credentials must exist; Fred does not alter server settings.
- This link requests a login method for any eligible account. Keycloak and Fred continue to enforce credentials, MFA, membership, suspension and permissions.
- On an issuer other than Keycloak, `prompt=login` requests fresh authentication but `kc_idp_hint` has no standard OIDC meaning. OIDC recommends ignoring unrecognized request parameters, but local Keycloak login is only promised with a Keycloak server. Document this without adding provider detection or arbitrary query-parameter forwarding. See https://openid.net/specs/openid-connect-core-1_0.html#AuthRequest.
- A cached account could mask the request or a retained flag could repeat it. Prioritize the explicit request over cached-user restoration and consume the flag before storing the return route.
- The capability exists in the merged portability change but has not been synced to main specs. Reuse its name and add only this requirement; reconcile both deltas when syncing, preserving existing lifecycle requirements.

## Migration Plan

Ship the frontend addition with an English migration note. There are no required operator or schema changes. Optional use requires a compatible Keycloak Browser flow and a local password. Verify both normal SSO login and the explicit local-login link in a real Keycloak browser session before rollout. Rollback restores the previous frontend and leaves Keycloak configuration unchanged.
