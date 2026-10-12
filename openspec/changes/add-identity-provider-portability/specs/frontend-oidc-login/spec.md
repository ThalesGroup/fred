## Purpose

Defines how the Fred frontend signs people in, keeps their session alive and signs them out with Keycloak or with any OIDC provider, and which Keycloak-only features it hides.

## ADDED Requirements

### Requirement: The frontend receives its provider settings from the control plane

`/frontend/config` `user_auth` SHALL include `provider`, `scope` and `user_directory` in addition to `enabled`, `realm_url` and `client_id`. Missing values SHALL mean `keycloak`, no scope and `keycloak`.

#### Scenario: Keycloak deployment

- **GIVEN** a backend without the new settings
- **WHEN** the frontend loads its configuration
- **THEN** it keeps the existing Keycloak configuration defaults and uses the common OIDC browser lifecycle

### Requirement: Sign-in uses the configured provider

For both `provider: keycloak` and `provider: oidc`, the frontend SHALL create an `oidc-client-ts` browser client from the issuer behind `KeyCloakService`, SHALL NOT require a `…/realms/<realm>` URL, and SHALL use Authorization Code with PKCE (S256). Both providers SHALL request `openid profile` plus the configured API scope; `provider: oidc` SHALL additionally request `offline_access`. Keycloak SHALL NOT require an offline-access grant for ordinary browser sign-in and refresh. The API bearer SHALL be the access token, not the ID token. Sign-in SHALL redirect to the provider's own login page.

#### Scenario: Entra sign-in

- **GIVEN** `provider: oidc`, an Entra issuer and `scope: api://fred-api/access_as_user`
- **WHEN** an unauthenticated person opens Fred
- **THEN** they are redirected to the Microsoft sign-in page
- **AND** after sign-in, API calls carry an access token whose audience is the Fred API

#### Scenario: Ordinary Keycloak sign-in without offline grants

- **GIVEN** a Keycloak client and user authorized for ordinary browser login but not offline tokens
- **WHEN** Fred starts sign-in with the default scope configuration
- **THEN** it requests `openid profile` with PKCE and the code exchange does not require an offline-access grant

### Requirement: Session renewal and sign-out work with the provider

For either provider, the frontend SHALL restore a valid session on reload, renew the access token in the browser before expiry (using a refresh token or silent authorization), reject a failed refresh without replaying an invalidated token, and sign out through the provider's `end_session_endpoint`, returning to Fred. There SHALL be no parallel `keycloak-js` browser lifecycle. Keycloak endpoint and claim defaults SHALL remain compatible.

#### Scenario: Long session

- **GIVEN** a signed-in person
- **WHEN** their access token approaches expiry
- **THEN** a new token is obtained without a visible redirect

Definitive renewal refusals (`invalid_grant`, `login_required`, `interaction_required`, `consent_required`, `account_selection_required`) SHALL invalidate in-memory access/refresh tokens and remove the stored OIDC user. Transient network/provider errors and timeouts SHALL preserve an otherwise unexpired bearer and permit retry. Error classification SHALL use the structured error code, not an error message or HTTP status alone. Existing boolean refresh results and provider sign-out behavior SHALL remain compatible.

#### Scenario: Definitive refresh refusal

- **GIVEN** a valid stored browser session for either provider
- **WHEN** renewal returns a definitive refusal
- **THEN** all coalesced callers receive `false`, getters expose no access/refresh token or claims, and the stored OIDC user is removed
- **AND** reloading cannot restore the refused session
- **AND** no late refresh or login callback can restore its invalidated generation

#### Scenario: Transient provider failure

- **GIVEN** an access token that has not expired
- **WHEN** renewal fails because of a network error, timeout or transient provider error
- **THEN** renewal returns `false`, the valid bearer remains available, and a subsequent renewal may succeed
- **AND** an expired bearer is never exposed

#### Scenario: Stored-user cleanup fails

- **GIVEN** a definitive renewal refusal and unavailable browser storage cleanup
- **WHEN** removal of the stored OIDC user fails
- **THEN** refresh still resolves `false` and no old token or claims are exposed by the current browser session

#### Scenario: Timed-out renewal and its retry succeed together

- **GIVEN** a timed-out renewal and a newer retry whose successful responses arrive together
- **WHEN** the SDK stores both results before Fred validates their generations
- **THEN** the live token, stored user and proactive renewal timer follow the accepted generation
- **AND** the accepted token is renewed before its own expiry

#### Scenario: Sign-out

- **GIVEN** a signed-in person
- **WHEN** they sign out
- **THEN** their provider session ends and they return to Fred's start page

### Requirement: The browser identifies the person exactly as the backends do

The frontend SHALL derive the user id from the configured identity claim and, for an `oidc` provider with a non-UUID value, SHALL apply the same `uuid5` derivation as the backends, so that `personal-<uid>` identifiers match. The frontend SHALL read roles from the configured roles claim when one is set.

#### Scenario: Personal space on Entra

- **GIVEN** `claims.uid: oid`
- **WHEN** a person opens their personal space
- **THEN** the team id used by the browser equals `personal-<oid>`, the id the backends authorize

#### Scenario: Non-UUID subject

- **GIVEN** `provider: oidc`, issuer `I` and a token whose identity claim is `00u1abc`
- **WHEN** the browser and a backend each derive the user id
- **THEN** both obtain `uuid5(NAMESPACE_URL, "I#00u1abc")`

#### Scenario: Debug role from a flat roles claim

- **GIVEN** `roles_claim: [roles]` and a token with `"roles": ["admin"]`
- **WHEN** the frontend evaluates the person's capabilities
- **THEN** the admin-only debug capability is available

### Requirement: Keycloak-only features are hidden

Without an explicit Keycloak realm configuration, the password-grant probe of the admin self-test SHALL be unavailable without an error. The credential-expiry scenario SHALL remain available for any authenticated OIDC session. With `user_directory: local`, the user administration page SHALL NOT offer user creation.

#### Scenario: Self-test on Entra

- **GIVEN** `provider: oidc`
- **WHEN** an administrator opens the self-test page
- **THEN** the "test another profile" probe is not offered and no Keycloak URL is called

#### Scenario: Keycloak uses the common OIDC implementation

- **GIVEN** the existing Keycloak realm and UI client configuration
- **WHEN** a person signs in, reloads Fred, renews their session and signs out
- **THEN** all operations use the same OIDC browser implementation as other providers
- **AND** their user id, roles and personal-space id remain unchanged
- **AND** a late refresh after logout cannot restore the invalidated session
