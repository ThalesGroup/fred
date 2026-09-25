## Purpose

Defines how Fred backends and agent pods locate an identity provider, validate and interpret its tokens, obtain workload tokens and refuse inconsistent configurations, for Keycloak and for any standards-compliant OIDC provider.

## ADDED Requirements

### Requirement: Keycloak deployments are unaffected by default

Every setting introduced by this change SHALL be optional. When `security.user.provider` and `security.m2m.provider` are absent or `keycloak`, and no override is set, the system SHALL build the same endpoint URLs, read the same claims, apply the same audience and issuer checks and use the same user directory as before this change.

#### Scenario: Existing configuration

- **GIVEN** a configuration file from before this change
- **WHEN** a service starts and validates a Keycloak access token
- **THEN** the JWKS URL is `{realm_url}/protocol/openid-connect/certs`
- **AND** roles are read from `resource_access.<client_id>.roles`, the username from `preferred_username` and the identity from `sub`
- **AND** no discovery request is made

### Requirement: An OIDC provider is located by discovery

When `provider` is `oidc`, the system SHALL treat `realm_url` as the issuer, fetch `{issuer}/.well-known/openid-configuration` once at startup and use its `jwks_uri` and `token_endpoint`. Explicit `jwks_url` and `token_url` settings SHALL take precedence over discovered values. The system SHALL refuse to start if discovery fails or if the discovered `issuer` differs from the configured issuer (ignoring a trailing slash).

#### Scenario: Discovery succeeds

- **GIVEN** `provider: oidc` and `realm_url: https://login.microsoftonline.com/<tid>/v2.0`
- **WHEN** the service starts
- **THEN** it validates token signatures with keys from the discovered `jwks_uri`
- **AND** it requests workload tokens from the discovered `token_endpoint`

#### Scenario: Issuer mismatch

- **GIVEN** a discovery document whose `issuer` differs from `realm_url`
- **WHEN** the service starts
- **THEN** startup fails with a message naming both issuers

#### Scenario: Discovery unreachable

- **GIVEN** an unreachable discovery URL
- **WHEN** the service starts
- **THEN** startup fails within the configured timeout
- **AND** the service does not fall back to Keycloak URLs

### Requirement: Token claims are read where the configuration says

The system SHALL read the identity, username, email, given name, family name and roles from configurable claim names or paths, with the Keycloak names as defaults. When `audience` is set, strict audience validation SHALL expect it instead of `client_id`. The authorized party SHALL still be read from `azp`, falling back to `client_id`.

#### Scenario: Entra roles

- **GIVEN** `roles_claim: [roles]` and a token with `"roles": ["service_agent"]`
- **WHEN** the token is validated
- **THEN** the principal is recognized as a service identity

#### Scenario: Distinct audience

- **GIVEN** strict audience validation, `client_id: fred-ui` and `audience: 6f1c…` (the API's client ID)
- **WHEN** a token with `aud: 6f1c…` is validated
- **THEN** it is accepted
- **AND** a token with `aud: fred-ui` is rejected

### Requirement: Identities are normalized without shared state

The user id SHALL be the configured identity claim when it is a UUID. For an `oidc` provider and a non-UUID value, the user id SHALL be `uuid5(NAMESPACE_URL, "<issuer>#<value>")`. The computation SHALL require no database, so that every backend and agent pod derives the same id.

#### Scenario: UUID identity

- **GIVEN** `claims.uid: oid` and a token with a UUID `oid`
- **WHEN** it is validated
- **THEN** the user id equals that `oid`

#### Scenario: Non-UUID identity

- **GIVEN** `provider: oidc`, issuer `I` and a token whose identity claim is `00u1abc`
- **WHEN** two different services validate it
- **THEN** both derive the same user id `uuid5(NAMESPACE_URL, "I#00u1abc")`

### Requirement: Workload tokens use the resolved endpoint and scope

Every client-credentials and refresh-token request SHALL use the resolved token endpoint. Workload token requests SHALL send `security.m2m.scope` when it is set. This SHALL apply to the workload token provider, the person-token refresher and the shared client-credentials helper.

#### Scenario: Entra client credentials

- **GIVEN** `m2m.provider: oidc` and `m2m.scope: api://fred-api/.default`
- **WHEN** a backend requests a workload token
- **THEN** the request is sent to the discovered token endpoint with that scope

### Requirement: Inconsistent provider configurations stop startup

The system SHALL refuse to start when `security.user.provider` is `oidc` and any of the following is true:

- `security.delegation.service_accounts_only` is true;
- delegation is in use and `security.delegation.caller_roles_claim` is unset;
- `security.user_directory` is `keycloak`.

#### Scenario: Keycloak-only delegation marker

- **GIVEN** `provider: oidc` and `service_accounts_only: true`
- **WHEN** the service starts
- **THEN** startup fails with a message explaining that this option relies on Keycloak service-account markers

#### Scenario: Missing caller roles claim

- **GIVEN** `provider: oidc`, `accept_delegated_calls: true` and no `caller_roles_claim`
- **WHEN** the service starts
- **THEN** startup fails instead of rejecting every delegated call at request time

### Requirement: Startup diagnostics accept non-Keycloak issuers

Startup checks, logging and diagnostics SHALL NOT fail or report an error because `realm_url` is not of the form `…/realms/<realm>` when `provider` is `oidc`. The Keycloak realm-format check SHALL remain in force when `provider` is `keycloak`.

#### Scenario: Entra issuer at startup

- **GIVEN** `provider: oidc` with an Entra issuer
- **WHEN** control plane, knowledge flow and the runtime start
- **THEN** no realm-parsing error is raised or logged

#### Scenario: Malformed Keycloak URL

- **GIVEN** `provider: keycloak` and a `realm_url` without `/realms/`
- **WHEN** knowledge flow starts
- **THEN** startup fails as it does today

### Requirement: Environment-configured applications accept the same provider settings

The shared first-party configuration built from the environment SHALL accept optional variables for the provider, audience, login scope, roles claim, identity claim, workload scope and directory source. When they are absent, the resulting configuration SHALL equal today's.

#### Scenario: First-party app on Entra

- **GIVEN** `OIDC_PROVIDER=oidc`, `OIDC_AUDIENCE`, `OIDC_ROLES_CLAIM=roles`, `OIDC_UID_CLAIM=oid` and `OIDC_M2M_SCOPE` set
- **WHEN** a first-party application builds its security configuration
- **THEN** it validates Entra tokens and obtains workload tokens with the given scope

#### Scenario: Unchanged environment

- **GIVEN** only today's `KEYCLOAK_*` variables
- **WHEN** a first-party application builds its security configuration
- **THEN** the configuration equals the one built before this change
