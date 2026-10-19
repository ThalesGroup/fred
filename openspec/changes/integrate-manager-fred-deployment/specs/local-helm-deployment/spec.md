## ADDED Requirements

### Requirement: Fred deploys Rust through the stable control-plane contract
The reconstruction deployment SHALL work with the unchanged factory swift definition through `make k3d-app APP=fred DIR=../fred`. It SHALL build the control-plane-backend image from Rust manager and run exactly control-plane-backend, control-plane-worker, knowledge-flow-backend, knowledge-flow-worker and frontend. API/worker pairs SHALL share their image. It MUST NOT execute Python control-plane, Alembic from its image or fred-agents.

#### Scenario: The developer deploys an ordinary checkout
- **WHEN** the unchanged factory builds and renders the reconstruction checkout
- **THEN** three images serve the five application workloads
- **AND** instance addresses, secrets and migration enablement work without a manager overlay or new Keycloak client

#### Scenario: Both entry points remain available
- **WHEN** the UI calls the manager path and the factory calls the control-plane bootstrap path
- **THEN** both reach the Rust implementation
- **AND** the existing UI components and layout remain unchanged

### Requirement: Upgrading the Fred release preserves manager state
The deployment SHALL preserve database/schema, OpenFGA store/model, identities, folders, roles, bootstrap, consent and lifecycle queue identities. It SHALL replace manager-named application resources under the same Fred release without resetting infrastructure. It MUST NOT automatically uninstall a separate release.

#### Scenario: An integrated manager deployment is upgraded
- **WHEN** the developer upgrades the existing fred-app release
- **THEN** the same manager data and grants are used by the control-plane-named Rust workloads
- **AND** a subsequent deployment converges on the same five workloads

#### Scenario: A standalone manager still exists
- **WHEN** the live install detects a manager Deployment owned by another release
- **THEN** it refuses coexistence and requires explicit operator retirement of that release
