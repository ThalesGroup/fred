## Purpose

Defines how the Fred frontend signs people in, keeps their session alive and signs them out with Keycloak or with any OIDC provider, and which Keycloak-only features it hides.

## ADDED Requirements

### Requirement: The frontend receives its provider settings from the control plane

`/frontend/config` `user_auth` SHALL include `provider`, `scope` and `user_directory` in addition to `enabled`, `realm_url` and `client_id`. Missing values SHALL mean `keycloak`, no scope and `keycloak`.

#### Scenario: Keycloak deployment

- **GIVEN** a backend without the new settings
- **WHEN** the frontend loads its configuration
- **THEN** it behaves exactly as before this change

### Requirement: Sign-in uses the configured provider

With `provider: oidc`, the frontend SHALL create its client in generic OIDC mode from the issuer, SHALL NOT require a `…/realms/<realm>` URL, SHALL use Authorization Code with PKCE (S256), and SHALL request the configured scope. Sign-in SHALL redirect to the provider's own login page.

#### Scenario: Entra sign-in

- **GIVEN** `provider: oidc`, an Entra issuer and `scope: api://fred-api/access_as_user`
- **WHEN** an unauthenticated person opens Fred
- **THEN** they are redirected to the Microsoft sign-in page
- **AND** after sign-in, API calls carry an access token whose audience is the Fred API

### Requirement: Session renewal and sign-out work with the provider

With `provider: oidc`, the frontend SHALL renew the access token in the browser before expiry and SHALL sign out through the provider's `end_session_endpoint`, returning to Fred.

#### Scenario: Long session

- **GIVEN** a signed-in person
- **WHEN** their access token approaches expiry
- **THEN** a new token is obtained without a visible redirect

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

With `provider: oidc`, the password-grant probe of the admin self-test and the credential-expiry self-test scenario SHALL be unavailable without an error. With `user_directory: local`, the user administration page SHALL NOT offer user creation.

#### Scenario: Self-test on Entra

- **GIVEN** `provider: oidc`
- **WHEN** an administrator opens the self-test page
- **THEN** the "test another profile" probe is not offered and no Keycloak URL is called
