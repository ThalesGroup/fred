## ADDED Requirements

### Requirement: Reproducible manager HTTP client

The service SHALL publish a machine-generated OpenAPI contract for its implemented HTTP routes and the frontend SHALL generate its client and types from that contract through Make targets equivalent to the other components. Generation SHALL require neither running services nor runtime secrets. The contract SHALL preserve authentication, request formats, response status/body shapes, enumerated roles, nullability and flattened response fields.

#### Scenario: Deterministic generation
- **WHEN** a developer runs manager `make generate-openapi` and frontend `make update-fred-manager-api` twice
- **THEN** the resulting schema and client are identical and the frontend typechecks
- **AND** `make update-all-apis` includes manager generation

#### Scenario: Binary ZIP transport
- **WHEN** the frontend sends an import through the manager client integration
- **THEN** it sends one multipart `file` with the operator bearer to `/fred-manager/v1/import-export/import`
- **AND** it consumes the generated completed-report type without expecting a task ID

### Requirement: Manager-authorized provisioning page

The UI SHALL offer provisioning to manager platform administrators using manager authority, independently of control-plane administrative roles. The existing shell admission guards SHALL remain in force. The page SHALL accept a ZIP, prevent duplicate submissions while pending, display completion counts only after success, and present failures with additive-replay guidance without claiming rollback.

#### Scenario: Complete and replay an import
- **GIVEN** an admitted manager platform administrator with sufficient authority for the bundle
- **WHEN** the operator selects and imports the Make-generated demo ZIP
- **THEN** the page shows the completed identity, space and grant counts from the service
- **AND** replay preserves committed identities and space IDs

#### Scenario: Authority unavailable or denied
- **WHEN** manager authority is loading, unavailable or excludes platform admin
- **THEN** the page does not enable provisioning
- **AND** it distinguishes an unavailable authority service from a confirmed access refusal

#### Scenario: Rejected or interrupted import
- **WHEN** the service rejects a legacy ZIP, returns an import failure, or the connection is lost
- **THEN** the page shows an error and no success report for that attempt
- **AND** it explains that effects can remain and replay requires correcting the cause

### Requirement: Repeatable browser acceptance

An automated browser journey SHALL exercise the provisioning page and actual manager HTTP API with disposable Keycloak, PostgreSQL and OpenFGA. It SHALL import the Make-generated ZIP, verify persisted hierarchy and roles, replay without duplicate spaces, and exercise access refusal and unsupported bundle feedback. Test setup SHALL leave unrelated development data untouched.

#### Scenario: Run browser acceptance repeatedly
- **WHEN** the developer runs the documented browser test command on a machine with its prerequisites
- **THEN** it creates isolated test state, exercises the import journey without manual curl or UI actions, and cleans up its services
- **AND** its assertions fail if the real import, replay or authorization behavior regresses
