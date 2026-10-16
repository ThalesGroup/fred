## ADDED Requirements

### Requirement: Explicit one-time Keycloak local login

When browser security is enabled, opening an initial Fred entry URL with `keycloak-login=true` SHALL start a fresh interactive authorization request containing `kc_idp_hint=` with an empty value and `prompt=login`, for both `provider: keycloak` and `provider: oidc`. Fred SHALL NOT gate this request on the provider setting or issuer URL shape. This request SHALL take precedence over restoring a cached authenticated Fred session. Fred SHALL clear its previous local session before initiating the request, preserve Authorization Code with PKCE S256 and callback validation, and SHALL NOT perform provider logout as part of this request.

Fred SHALL consume the flag before leaving for authorization and restore the requested local path, remaining query parameters and fragment after successful login. The return destination SHALL remain in local OIDC state, with an opaque state value sent to the identity provider. Callback processing SHALL take precedence over interpreting the flag, and a callback or reload SHALL NOT repeat the explicit request. Ordinary login without exact opt-in and insecure mode SHALL retain their existing behavior. This option SHALL NOT grant or bypass identity-provider credentials, MFA or any Fred admission or authorization requirement. Local Keycloak login SHALL depend on the authorization server supporting that login path; sending the flag to another issuer SHALL NOT imply that issuer supports Keycloak-specific behavior.

#### Scenario: Explicit entry while signed out

- **WHEN** a signed-out person opens `/help?topic=agents&keycloak-login=true#tools` in a Keycloak deployment
- **THEN** authorization contains an explicitly present empty `kc_idp_hint`, `prompt=login`, an opaque state and an S256 PKCE challenge
- **AND** the return destination is `/help?topic=agents#tools`, kept outside the provider request

#### Scenario: Explicit entry while already signed in

- **WHEN** a person with a valid stored Fred session opens a URL with `keycloak-login=true`
- **THEN** Fred initiates fresh interactive authentication instead of restoring or refreshing that cached session
- **AND** the old local bearer is unavailable, provider logout is not called, and late results cannot restore the old session

#### Scenario: Keycloak connected through generic OIDC

- **WHEN** Fred uses `provider: oidc` with Keycloak as its issuer and a person opens a URL with `keycloak-login=true`
- **THEN** Fred sends the same empty `kc_idp_hint` and `prompt=login` as with `provider: keycloak`
- **AND** the explicit login preserves PKCE, callback validation and the cleaned return destination

#### Scenario: Successful callback and reload

- **WHEN** the explicit login succeeds and Fred processes its callback
- **THEN** Fred restores the requested page with the flag removed and exposes the newly authenticated person's token and claims
- **AND** reloading follows normal session restoration without forcing another login

#### Scenario: Callback handling has priority

- **WHEN** Fred receives an OIDC success or error callback with a state value and a query flag
- **THEN** it processes the callback through its existing validation and error handling rather than starting another explicit local login

#### Scenario: Entry without exact opt-in

- **WHEN** an entry URL for either provider setting omits the flag or has `keycloak-login=false` or an empty flag
- **THEN** Fred uses its ordinary cached-session or provider-login behavior without adding either authorization parameter

#### Scenario: Explicit request with a non-Keycloak issuer

- **WHEN** a person opens Fred with the flag and the configured OIDC issuer is not Keycloak
- **THEN** Fred still sends the explicit authorization parameters and the issuer's authentication and error handling remain authoritative
- **AND** Fred does not choose a different issuer or promise a local Keycloak login form

#### Scenario: Insecure mode

- **WHEN** a person opens Fred with the flag in a security-disabled deployment
- **THEN** the flag does not force authentication or initiate an OIDC authorization request

#### Scenario: Keycloak policy remains authoritative

- **WHEN** the explicit login reaches a Keycloak flow that requires organization identification or does not permit local password login
- **THEN** Keycloak's configured authentication steps and failures still apply
- **AND** Fred does not bypass provider checks or grant application permissions from the URL flag
