## Purpose

Defines the local environments, provided by the sibling `fred-deployment-factory` repository, that exercise Fred's generic identity-provider paths on a laptop without a cloud tenant.

## ADDED Requirements

### Requirement: The default local stack is unchanged

The test bench SHALL be opt-in. `make docker-up`, `make docker-start` and the default Keycloak provisioning SHALL behave exactly as before this change.

#### Scenario: Plain developer setup

- **GIVEN** a developer who never runs the new targets
- **WHEN** they run `make docker-up`
- **THEN** the realm, clients, roles and mappers are identical to the baseline

### Requirement: Keycloak can present a generic OIDC token shape

A factory target SHALL reconfigure the local Keycloak so that user and workload access tokens carry a flat `roles` claim and a `fred-api` audience, as Entra does, with a matching revert target. A strict option SHALL remove `resource_access` from those tokens and the Admin API roles from the service accounts.

#### Scenario: Generic shape

- **GIVEN** `make keycloak-generic-oidc`
- **WHEN** the `agentic` service account obtains a token
- **THEN** the token has `aud` containing `fred-api` and `roles` containing `service_agent` and `delegation_caller`

#### Scenario: Strict shape exposes hidden dependencies

- **GIVEN** `make keycloak-generic-oidc STRICT=1` and Fred configured with `provider: oidc` and `user_directory: local`
- **WHEN** the full local validation runs
- **THEN** it passes without any Admin API call and without reading `resource_access`

#### Scenario: Revert

- **GIVEN** the generic shape is applied
- **WHEN** `make keycloak-generic-oidc-revert` runs
- **THEN** the baseline token shape and service-account roles are restored

### Requirement: A non-Keycloak provider is available locally

A factory target SHALL start a mock OIDC provider, distinct from Keycloak, that supports discovery, JWKS, authorization code with PKCE, client credentials and refresh, and issues non-UUID subjects and tokens longer than one hour.

#### Scenario: Fred without Keycloak

- **GIVEN** `make mock-oidc-up`, Fred configured with the mock issuer, and the Keycloak container stopped
- **WHEN** a person signs in, chats with an agent that reads documents, and an administrator searches users
- **THEN** every step succeeds

### Requirement: The local directory can be prepared before import

A factory script SHALL record every demo user in Fred's local directory by signing each one in once, so that the demo bundle import succeeds in `local` mode.

#### Scenario: Demo import in local mode

- **GIVEN** the demo users are seeded in Keycloak and `user_directory: local`
- **WHEN** the warm-up script runs and the demo bundle is imported
- **THEN** the import succeeds and every named user is resolved
