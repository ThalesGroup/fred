## MODIFIED Requirements

### Requirement: Accept the configured version

The system SHALL accept and persist the configured GCU version as an opaque string in the existing user record, with its acceptance timestamp. Each acceptance SHALL replace the previously stored version and timestamp. User details SHALL expose the stored version or null, without a fixed version enumeration or GCU acceptance history. The Python user-store API SHALL accept string versions only and SHALL NOT export the retired `GcuVersionsType` from the user model, `fred_core.users` or `fred_core`.

#### Scenario: Reaccept a newer version
- **GIVEN** a user has accepted `v1` and the active configured version is `v2`
- **WHEN** the user accepts the current terms
- **THEN** the acceptance request succeeds and user details report `v2` with the new acceptance timestamp

#### Scenario: Deployment-owned version identifier
- **GIVEN** the active configured version is `2026-10`
- **WHEN** a user accepts the terms
- **THEN** the persisted and returned version is exactly `2026-10`

#### Scenario: String-only Python store input
- **WHEN** a Python caller records acceptance through the user-store API
- **THEN** the supported input type is `str` and the provided version is persisted unchanged

#### Scenario: Retired Python enum export
- **WHEN** a Python consumer loads the user model, `fred_core.users` or `fred_core`
- **THEN** `GcuVersionsType` is absent from each public module surface
